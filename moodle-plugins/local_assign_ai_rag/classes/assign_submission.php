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

namespace local_assign_ai_rag;

use local_assign_ai_rag\api\client;
use stdClass;

/**
 * Class assign_submission
 *
 * Handles submission processing with RAG AI grading.
 * Uses the same pipeline as main_service RAG system.
 *
 * @package    local_assign_ai_rag
 * @copyright  2025 Glenn H. K. M.
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */
class assign_submission {
    /** Initial status before processing with AI. */
    public const STATUS_INITIAL = 'initial';
    /** Pending status awaiting human review. */
    public const STATUS_PENDING = 'pending';
    /** Queued status when review-all has been scheduled. */
    public const STATUS_QUEUED = 'queued';
    /** Processing status when ad-hoc task is handling the record. */
    public const STATUS_PROCESSING = 'processing';
    /** Approved status after human review or AI grading. */
    public const STATUS_APPROVED = 'approved';
    /** Rejected status after human review. */
    public const STATUS_REJECTED = 'rejected';

    /** @var stdClass User ID of the author of the submission. */
    private stdClass $user;

    /** @var stdClass Submission record from {assign_submission}. */
    private stdClass|false $submission;

    /** @var \assign Assign instance */
    private \assign $assign;

    /** @var stdClass Assignment instance */
    private stdClass $assigninstance;

    /** @var stdClass Course instance */
    private stdClass $course;

    /**
     * Constructor.
     *
     * @param int $userid User ID of the author of the submission.
     * @param \assign $assign Assign instance.
     */
    public function __construct(int $userid, \assign $assign) {
        global $DB;
        $this->assign = $assign;
        $this->user = $DB->get_record('user', ['id' => $userid, 'deleted' => 0, 'suspended' => 0], '*', MUST_EXIST);
        $this->submission = $assign->get_user_submission($userid, false);
        $this->assigninstance = $assign->get_instance();
        $this->course = $assign->get_course();
    }

    /**
     * Processes a submission against RAG AI logic depending on autograde configuration.
     *
     * When autograde is enabled, sends the payload to the RAG AI server and stores
     * the AI response in the single pending record for this assignment/user. The
     * grade is applied to the gradebook only when a grader user is configured;
     * otherwise the result stays pending for teacher review. Failed AI responses
     * are never applied: the record is reset to the initial state so the teacher
     * can retry with "Review with AI".
     *
     * @return void
     * @throws \moodle_exception When the RAG server cannot grade the submission.
     */
    public function process_submission_ai(): void {
        global $DB;

        if (!$this->submission || !$this->user) {
            return;
        }

        // Only process submitted attempts.
        if ($this->submission->status !== ASSIGN_SUBMISSION_STATUS_SUBMITTED) {
            return;
        }

        $assignment = $this->assigninstance;
        $cmid = (int)$this->assign->get_course_module()->id;
        $existing = self::get_pending_record($cmid, (int)$this->user->id);

        if (!local_assign_ai_rag_is_autograde_enabled($this->assign)) {
            // Autograde disabled: make sure a basic record exists for later review.
            if (!$existing) {
                self::create_pending_submission($this->build_initial_record($cmid));
            }
            return;
        }

        try {
            $data = self::parse_ai_response(client::send_to_ai($this->build_payload()));
        } catch (\Throwable $e) {
            // Never leave a half-processed or error-only result behind.
            $reset = self::empty_ai_fields() + ['status' => self::STATUS_INITIAL];
            if ($existing) {
                self::update_pending_submission((int)$existing->id, $reset);
            } else {
                self::create_pending_submission($this->build_initial_record($cmid));
            }
            throw $e;
        }

        $config = local_assign_ai_rag_get_assignment_config((int)$assignment->id);
        $graderid = (!empty($config) && !empty($config->graderid)) ? (int)$config->graderid : 0;

        // Without a grader nothing is written to the gradebook, so the result must
        // stay visible for teacher review instead of being marked approved.
        $data['status'] = $graderid ? self::STATUS_APPROVED : self::STATUS_PENDING;

        if ($existing) {
            $recordid = (int)$existing->id;
            self::update_pending_submission($recordid, $data);
        } else {
            $record = $this->build_initial_record($cmid);
            foreach ($data as $key => $value) {
                $record->$key = $value;
            }
            $recordid = self::create_pending_submission($record);
        }

        if ($graderid) {
            $record = $DB->get_record('local_assign_ai_rag_pending', ['id' => $recordid], '*', MUST_EXIST);
            local_assign_ai_rag_apply_ai_feedback($this->assign, $record, $graderid);
        }
    }

    /**
     * Processes a submission for the "Review with AI" action.
     *
     * Always sends the submission payload to the RAG AI server (regardless of
     * autograde setting) and stores the AI response in the pending table with
     * status set to STATUS_PENDING for manual review/approval.
     *
     * @param int $pendingid Pending record ID to update in local_assign_ai_rag_pending.
     * @return void
     * @throws \moodle_exception When the RAG server cannot grade the submission;
     *         the caller resets the record so an error is never approved as a grade.
     */
    public function process_submission_ai_review(int $pendingid): void {
        global $DB;
        if (!$this->submission || !$this->user) {
            return;
        }
        if ($this->submission->status !== ASSIGN_SUBMISSION_STATUS_SUBMITTED) {
            return;
        }

        // Find existing pending record to update.
        $existing = $DB->get_record('local_assign_ai_rag_pending', ['id' => $pendingid], '*', MUST_EXIST);

        $data = self::parse_ai_response(client::send_to_ai($this->build_payload()));
        $data['status'] = self::STATUS_PENDING;
        self::update_pending_submission($existing->id, $data);
    }

    /**
     * Convert a RAG client response into pending-record fields.
     *
     * @param array $response Response from client::send_to_ai().
     * @return array Pending record fields (without status).
     * @throws \moodle_exception When the RAG server reported a grading failure.
     */
    public static function parse_ai_response(array $response): array {
        if (array_key_exists('success', $response) && !$response['success']) {
            $error = trim((string)($response['error'] ?? $response['feedback'] ?? ''));
            throw new \moodle_exception('aigradingfailed', 'local_assign_ai_rag', '',
                $error !== '' ? $error : 'Unknown error');
        }

        $grade = (isset($response['grade']) && is_numeric($response['grade'])) ? (float)$response['grade'] : null;
        $confidence = (isset($response['confidence']) && is_numeric($response['confidence']))
            ? max(0.0, min(1.0, (float)$response['confidence']))
            : null;

        return [
            'message' => isset($response['feedback']) ? (string)$response['feedback'] : null,
            // Keep decimals: the column has the same precision as assign_grades.grade.
            'grade' => $grade,
            'rubric_response' => !empty($response['rubric_scores'])
                ? json_encode($response['rubric_scores'], JSON_UNESCAPED_UNICODE) : null,
            'citations' => !empty($response['citations'])
                ? json_encode($response['citations'], JSON_UNESCAPED_UNICODE) : null,
            'confidence' => $confidence,
            'retrieved_docs' => !empty($response['retrieved_documents'])
                ? json_encode($response['retrieved_documents'], JSON_UNESCAPED_UNICODE) : null,
        ];
    }

    /**
     * Get the pending record for an assignment/user, tolerating legacy duplicates.
     *
     * @param int $cmid Assignment course module ID.
     * @param int $userid Student user ID.
     * @return stdClass|null Most recent pending record, or null.
     */
    public static function get_pending_record(int $cmid, int $userid): ?stdClass {
        global $DB;

        $records = $DB->get_records('local_assign_ai_rag_pending',
            ['assignmentid' => $cmid, 'userid' => $userid], 'id DESC', '*', 0, 1);
        return $records ? reset($records) : null;
    }

    /**
     * AI result fields cleared when a record goes back to the initial state.
     *
     * @return array
     */
    private static function empty_ai_fields(): array {
        return [
            'message' => null,
            'grade' => null,
            'rubric_response' => null,
            'citations' => null,
            'confidence' => null,
            'retrieved_docs' => null,
        ];
    }

    /**
     * Build a new pending record in the initial state for this submission.
     *
     * @param int $cmid Assignment course module ID.
     * @return stdClass
     */
    private function build_initial_record(int $cmid): stdClass {
        return (object) ([
            'courseid' => $this->course->id,
            'assignmentid' => $cmid,
            'userid' => $this->user->id,
            'title' => $this->assigninstance->name,
            'status' => self::STATUS_INITIAL,
        ] + self::empty_ai_fields());
    }

    /**
     * Create a pending AI submission record.
     *
     * @param stdClass $record Pending record payload.
     * @return int New record ID.
     */
    public static function create_pending_submission(stdClass $record): int {
        global $DB, $USER;

        $transaction = $DB->start_delegated_transaction();
        try {
            $now = time();
            $record->status = $record->status ?? self::STATUS_PENDING;
            $record->usermodified = $USER->id;
            $record->timecreated = $now;
            $record->timemodified = $now;

            $id = $DB->insert_record('local_assign_ai_rag_pending', $record);
            $transaction->allow_commit();
            return $id;
        } catch (\Throwable $e) {
            $transaction->rollback($e);
            throw $e;
        }
    }

    /**
     * Update an existing pending AI submission record.
     *
     * @param int $id Record ID.
     * @param array $data Data to update.
     * @return bool True on success, false on failure.
     */
    public static function update_pending_submission(int $id, array $data): bool {
        global $DB, $USER;

        $record = $DB->get_record('local_assign_ai_rag_pending', ['id' => $id]);
        if (!$record) {
            return false;
        }

        $transaction = $DB->start_delegated_transaction();
        try {
            foreach ($data as $key => $value) {
                $record->$key = $value;
            }
            $record->timemodified = time();
            if (!isset($record->usermodified)) {
                $record->usermodified = $USER->id ?? null;
            }

            $ok = $DB->update_record('local_assign_ai_rag_pending', $record);
            $transaction->allow_commit();
            return $ok;
        } catch (\Exception $e) {
            $transaction->rollback($e);
            throw $e;
        }
    }

    /**
     * Retrieves the onlinetext content for a given submission.
     *
     * @param stdClass $submission Submission record from {assign_submission}.
     * @return string The submission text or empty string if none.
     */
    public static function get_submission_text(stdClass $submission): string {
        global $DB;
        $submissioncontent = '';
        $onlinetext = $DB->get_record('assignsubmission_onlinetext', ['submission' => $submission->id]);
        if ($onlinetext && !empty($onlinetext->onlinetext)) {
            $submissioncontent = $onlinetext->onlinetext;
        }
        return $submissioncontent;
    }

    /**
     * Build payload for RAG AI service.
     * Format matches the main_service RAG pipeline expectations.
     *
     * @return array The payload array.
     */
    private function build_payload(): array {
        global $DB;
        
        $course = $this->assign->get_course();
        $assignment = $this->assigninstance;
        $cmid = $this->assign->get_course_module()->id;
        
        // First, check for custom rubric in local_assign_ai_rag_rubric table.
        $customRubric = $DB->get_record('local_assign_ai_rag_rubric', ['assignmentid' => $cmid]);
        
        $rubricForRag = new \stdClass();  // Empty object {} for RAG server.
        $maxGrade = (float)$assignment->grade;
        
        if ($customRubric && !empty($customRubric->rubric_json)) {
            // Use custom rubric from our table.
            $rubricData = json_decode($customRubric->rubric_json, true);
            if ($rubricData && isset($rubricData['criteria'])) {
                // Convert to RAG format: {"criteria": {"Name": {"points": X, "description": "...", "levels": {...}}}}
                $rubricForRag = (object) ['criteria' => (object) $rubricData['criteria']];
                $maxGrade = (float)$customRubric->max_grade;
            }
        } else {
            // Fallback to Moodle's native rubric if available.
            $rubric = local_assign_ai_rag_build_rubric_json($this->assign);
            
            if ($rubric && !empty($rubric['criteria'])) {
                $criteria = [];
                foreach ($rubric['criteria'] as $criterion) {
                    $maxPoints = 0;
                    $levels = [];
                    foreach ($criterion['levels'] as $level) {
                        if ($level['points'] > $maxPoints) {
                            $maxPoints = $level['points'];
                        }
                        // Convert to levels format: {"excellent": "desc", "good": "desc", ...}
                        $levelName = $this->get_level_name($level['points'], $maxPoints);
                        $levels[$levelName] = $level['description'];
                    }
                    $criteria[$criterion['criterion']] = [
                        'points' => $maxPoints,
                        'description' => $criterion['criterion'],
                        'levels' => $levels
                    ];
                }
                $rubricForRag = (object) ['criteria' => (object) $criteria];
            }
        }

        // Get question from assignment intro/description.
        $question = strip_tags($assignment->intro);
        if (empty($question)) {
            $question = $assignment->name;
        }

        // Get student's answer.
        $essay = strip_tags(self::get_submission_text($this->submission));

        // Build payload matching main_service MoodleAssignRequest format.
        return [
            'course_id' => (string)$course->id,
            'question' => $question,
            'essay' => $essay,
            'rubric' => $rubricForRag,
            'maximum_grade' => $maxGrade,
        ];
    }

    /**
     * Get level name based on points ratio.
     *
     * @param float $points Current level points.
     * @param float $maxPoints Maximum points.
     * @return string Level name.
     */
    private function get_level_name(float $points, float $maxPoints): string {
        if ($maxPoints <= 0) {
            return 'poor';
        }
        $ratio = $points / $maxPoints;
        if ($ratio >= 0.9) {
            return 'excellent';
        } else if ($ratio >= 0.7) {
            return 'good';
        } else if ($ratio >= 0.5) {
            return 'fair';
        } else {
            return 'poor';
        }
    }
}
