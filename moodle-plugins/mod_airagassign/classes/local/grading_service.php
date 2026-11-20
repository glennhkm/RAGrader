<?php
// This file is part of Moodle - http://moodle.org/
//
// Moodle is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// Moodle is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with Moodle.  If not, see <http://www.gnu.org/licenses/>.

namespace mod_airagassign\local;

use mod_airagmaterial\local\rag_client;

/**
 * Grades airagassign submissions through the RAG API and stores the AI suggestion.
 *
 * Successful grading stores ai_grade/ai_feedback/confidence with status
 * 'ai_suggested'; the final grade is only written when the teacher confirms it.
 *
 * @package    mod_airagassign
 * @copyright  2026 RAGrader
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */
class grading_service {
    /** @var int Timeout in seconds for one grading request. */
    private const TIMEOUT = 120;

    /** @var rag_client|null RAG client, created on first use when not injected. */
    private ?rag_client $client;

    /**
     * Constructor.
     *
     * @param rag_client|null $client Injected client; defaults to the mod_airagassign settings.
     */
    public function __construct(?rag_client $client = null) {
        $this->client = $client;
    }

    /**
     * Grade a single submission using the RAG API.
     *
     * @param \stdClass $assign The assignment record
     * @param \stdClass $submission The submission record
     * @param \context_module $context The module context
     * @return array ['success' => bool, ...] with 'error' (and 'requestid' when a request was made) on failure
     */
    public function grade_submission(\stdClass $assign, \stdClass $submission, \context_module $context): array {
        global $DB;

        $rubric = rubric_builder::build((int)$assign->id);
        if (($assign->rubricmode ?? '') === 'moodle' && empty($rubric)) {
            return [
                'success' => false,
                'error' => get_string('moodlerubric_not_configured', 'airagassign'),
            ];
        }

        // Fail closed: every linked material must be fully vectorized, otherwise
        // retrieval would silently use only part of the selected knowledge base.
        $unready = material_scope::unready_materials((int)$assign->id);
        if (!empty($unready)) {
            return [
                'success' => false,
                'error' => get_string('linkedmaterials_not_ready', 'airagassign',
                    material_scope::describe_unready($unready, $context)),
            ];
        }

        $sourcefilter = material_scope::linked_filenames((int)$assign->id, (int)$context->id);
        if (empty($sourcefilter) && $DB->record_exists('airagassign_materials', ['assignid' => $assign->id])) {
            return [
                'success' => false,
                'error' => get_string('linkedmaterials_no_vectorized_files', 'airagassign'),
            ];
        }

        if ($assign->assignmode === 'quiz') {
            return $this->grade_quiz($assign, $submission, $rubric, $sourcefilter);
        }
        return $this->grade_essay($assign, $submission, $rubric, $sourcefilter);
    }

    /**
     * Persist an AI grading failure for teacher review and retry.
     *
     * @param int $submissionid Submission ID
     * @param string $error Error message
     * @param string $requestid API request ID, when available
     */
    public static function record_failure(int $submissionid, string $error, string $requestid = ''): void {
        global $DB;

        $cleanerror = trim(strip_tags($error));
        if ($cleanerror === '') {
            $cleanerror = 'Unknown grading error';
        }
        $cleanerror = \core_text::substr($cleanerror, 0, 4000);

        $DB->update_record('airagassign_submissions', (object)[
            'id' => $submissionid,
            'status' => 'grading_failed',
            'grading_error' => $cleanerror,
            'grading_requestid' => \core_text::substr(trim($requestid), 0, 64),
            'grading_started_at' => 0,
        ]);
    }

    /**
     * Clamp an API confidence value into the 0..1 range stored in the database.
     *
     * @param mixed $value Raw confidence from the RAG response
     * @return float Confidence between 0 and 1
     */
    public static function normalize_confidence($value): float {
        $confidence = is_numeric($value) ? (float)$value : 0.0;
        if (!is_finite($confidence)) {
            return 0.0;
        }
        return max(0.0, min(1.0, $confidence));
    }

    /**
     * Grade a quiz-mode submission (per-question grading).
     *
     * @param \stdClass $assign Assignment record
     * @param \stdClass $submission Submission record
     * @param array $rubric Rubric dictionary
     * @param array $sourcefilter Source filenames for scoped retrieval
     * @return array Result
     */
    private function grade_quiz(\stdClass $assign, \stdClass $submission, array $rubric, array $sourcefilter): array {
        global $DB;

        $questions = $DB->get_records('airagassign_questions', ['assignid' => $assign->id], 'sortorder ASC');
        $answers = $DB->get_records('airagassign_answers', ['submissionid' => $submission->id]);

        // Index answers by question ID.
        $answermap = [];
        foreach ($answers as $a) {
            $answermap[$a->questionid] = $a;
        }

        $numquestions = count($questions);
        if ($numquestions == 0) {
            return ['success' => false, 'error' => 'No questions defined'];
        }

        $gradeperquestion = (float)$assign->maximumgrade / $numquestions;
        $totalscore = 0;
        $allfeedback = [];
        $allerrors = [];
        $confidences = [];
        $failedrequestid = '';

        foreach ($questions as $question) {
            $answer = $answermap[$question->id] ?? null;
            if (!$answer) {
                continue;
            }

            $result = $this->call_api($this->payload($assign, $question->questiontext, $answer->answertext,
                $rubric, $gradeperquestion, $sourcefilter));

            if ($result['success']) {
                $qscore    = (float)($result['data']['score']    ?? 0);
                $qfeedback = $result['data']['feedback'] ?? '';

                // Store AI suggestion in separate columns — final score/feedback
                // is only written when the teacher confirms via grade_review.php.
                $answer->ai_score    = $qscore;
                $answer->ai_feedback = $qfeedback;
                $answer->ai_response = json_encode($result['data']);
                $DB->update_record('airagassign_answers', $answer);

                $totalscore += $qscore;
                $allfeedback[] = "Q" . ($question->sortorder + 1) . ": " . $qfeedback;
                $confidences[] = self::normalize_confidence($result['data']['confidence'] ?? 0);
            } else {
                $allerrors[] = "Q" . ($question->sortorder + 1) . ": " . ($result['error'] ?? 'Unknown error');
                $failedrequestid = $result['requestid'] ?? $failedrequestid;
            }
        }

        if (!empty($allerrors)) {
            return [
                'success' => false,
                'error' => implode('; ', $allerrors),
                'requestid' => $failedrequestid,
            ];
        }

        // Store AI suggestion — teacher must confirm via grade_review.php.
        $submission->ai_grade    = round($totalscore, 2);
        $submission->ai_feedback = implode("\n\n", $allfeedback);
        // The submission is only as trustworthy as its least certain answer, so the
        // minimum (not the mean) drives the HITL review signal in quiz mode.
        $submission->confidence  = empty($confidences) ? null : min($confidences);
        $this->mark_suggested($submission);

        return [
            'success'  => true,
            'ai_grade' => $submission->ai_grade,
            'feedback' => $submission->ai_feedback,
            'errors'   => $allerrors,
        ];
    }

    /**
     * Grade an essay-mode submission (single grading).
     *
     * @param \stdClass $assign Assignment record
     * @param \stdClass $submission Submission record
     * @param array $rubric Rubric dictionary
     * @param array $sourcefilter Source filenames for scoped retrieval
     * @return array Result
     */
    private function grade_essay(\stdClass $assign, \stdClass $submission, array $rubric, array $sourcefilter): array {
        global $DB;

        $answer = $DB->get_record('airagassign_answers', ['submissionid' => $submission->id]);
        if (!$answer) {
            return ['success' => false, 'error' => 'No essay answer found'];
        }

        $result = $this->call_api($this->payload($assign, $assign->essayprompt, $answer->answertext,
            $rubric, (float)$assign->maximumgrade, $sourcefilter));
        if (!$result['success']) {
            return $result;
        }

        $score    = (float)($result['data']['score']    ?? 0);
        $feedback = $result['data']['feedback'] ?? '';

        // Store AI suggestion in separate columns — score/feedback remain empty
        // until the teacher confirms the grade in grade_review.php.
        $answer->ai_score    = $score;
        $answer->ai_feedback = $feedback;
        $answer->ai_response = json_encode($result['data']);
        $DB->update_record('airagassign_answers', $answer);

        // Update submission with AI suggestion (NOT final grade).
        $submission->ai_grade    = round($score, 2);
        $submission->ai_feedback = $feedback;
        $submission->ai_response = json_encode($result['data']);
        $submission->confidence  = self::normalize_confidence($result['data']['confidence'] ?? 0);
        $this->mark_suggested($submission);

        return [
            'success'  => true,
            'ai_grade' => $submission->ai_grade,
            'feedback' => $feedback,
        ];
    }

    /**
     * Store a submission whose AI fields are set as 'ai_suggested'.
     *
     * @param \stdClass $submission Submission record with ai_grade, ai_feedback and confidence set
     */
    private function mark_suggested(\stdClass $submission): void {
        global $DB;

        $submission->status             = 'ai_suggested';
        $submission->grading_error      = null;
        $submission->grading_requestid  = null;
        $submission->grading_started_at = 0;
        $submission->timegraded         = time();
        $DB->update_record('airagassign_submissions', $submission);
    }

    /**
     * Build the /assign/answer payload.
     *
     * @param \stdClass $assign Assignment record
     * @param string|null $question Question or essay prompt
     * @param string|null $essay Student answer
     * @param array $rubric Rubric dictionary
     * @param float $maximumgrade Maximum grade for this answer
     * @param array $sourcefilter Source filenames for scoped retrieval
     * @return array Payload
     */
    private function payload(\stdClass $assign, ?string $question, ?string $essay, array $rubric,
            float $maximumgrade, array $sourcefilter): array {
        $payload = [
            'course_id' => $assign->course,
            'question' => $question,
            'essay' => $essay,
            'rubric' => $rubric,
            'maximum_grade' => $maximumgrade,
            'assignment_id' => $assign->id,
        ];
        if (!empty($sourcefilter)) {
            $payload['source_filter'] = array_values($sourcefilter);
        }
        return $payload;
    }

    /**
     * Call the RAG grading API.
     *
     * @param array $payload Request payload
     * @return array ['success' => true, 'data' => array, 'requestid' => string]
     *               or ['success' => false, 'error' => string, 'requestid' => string]
     */
    private function call_api(array $payload): array {
        $requestid = bin2hex(random_bytes(16));

        // FastAPI expects rubric to be a JSON object. In simple grading mode there
        // is no rubric, and PHP would encode an empty array as [] which triggers a
        // 422 validation error before the request reaches the grading logic.
        if (empty($payload['rubric'])) {
            $payload['rubric'] = new \stdClass();
        }

        $this->client ??= rag_client::for_component('mod_airagassign', self::TIMEOUT);
        $result = $this->client->grade($payload, $requestid);
        if ($result['success']) {
            return ['success' => true, 'data' => $result['data'], 'requestid' => $requestid];
        }

        $error = $result['error'] ?? 'Unknown error';
        if ($result['status'] === 200) {
            $data = $result['data'];
            $error = empty($data)
                ? 'Invalid JSON response from server'
                : ($data['error'] ?? $data['message'] ?? 'Server returned failure');
        }
        return [
            'success' => false,
            'error' => is_string($error) ? $error : (string)json_encode($error),
            'requestid' => $requestid,
        ];
    }
}
