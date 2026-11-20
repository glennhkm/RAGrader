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

use GuzzleHttp\Client;
use GuzzleHttp\Exception\ConnectException;
use GuzzleHttp\Handler\MockHandler;
use GuzzleHttp\HandlerStack;
use GuzzleHttp\Middleware;
use GuzzleHttp\Psr7\Request;
use GuzzleHttp\Psr7\Response;
use mod_airagmaterial\local\http_factory;

/**
 * Characterization tests for AI grading of submissions.
 *
 * @package    mod_airagassign
 * @category   test
 * @copyright  2026 RAGrader
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 * @covers     \mod_airagassign\local\grading_service
 * @covers     \mod_airagassign\task\grade_submission
 */
final class grading_service_test extends \advanced_testcase {
    /** @var array Guzzle request history. */
    private array $history = [];

    /** @var int[] Timeouts the HTTP factory was asked for. */
    private array $timeouts = [];

    /**
     * Route every RAG client through a mocked Guzzle handler.
     *
     * @param array $queue Responses or exceptions.
     */
    private function mock_http(array $queue): void {
        $this->history = [];
        $this->timeouts = [];
        $stack = HandlerStack::create(new MockHandler($queue));
        $stack->push(Middleware::history($this->history));
        $http = new Client(['handler' => $stack]);
        $factory = $this->createMock(http_factory::class);
        $factory->method('create')->willReturnCallback(function (int $timeout) use ($http) {
            $this->timeouts[] = $timeout;
            return $http;
        });
        \core\di::set(http_factory::class, $factory);
    }

    /**
     * Queue RAG server responses.
     *
     * @param array $responses List of [status, body array|string].
     */
    private function queue(array $responses): void {
        set_config('serverurl', 'http://rag.test/', 'mod_airagassign');
        set_config('apikey', 'k', 'mod_airagassign');
        $this->mock_http(array_map(fn($r) => new Response($r[0], ['Content-Type' => 'application/json'],
            is_string($r[1]) ? $r[1] : json_encode($r[1])), $responses));
    }

    /**
     * Make the RAG server unreachable.
     */
    private function queue_connection_error(): void {
        $this->queue([]);
        $this->mock_http([new ConnectException('Connection refused', new Request('POST', 'http://rag.test'))]);
    }

    /**
     * Requests the RAG server received.
     *
     * @return array List of [method, path, headers, body, json].
     */
    private function requests(): array {
        $out = [];
        foreach ($this->history as $entry) {
            $request = $entry['request'];
            $headers = [];
            foreach (array_keys($request->getHeaders()) as $name) {
                $headers[strtolower($name)] = $request->getHeaderLine($name);
            }
            $body = (string)$request->getBody();
            $out[] = ['method' => $request->getMethod(), 'path' => $request->getUri()->getPath(),
                'headers' => $headers, 'body' => $body, 'json' => json_decode($body, true)];
        }
        return $out;
    }

    /**
     * Grade through the code under test.
     *
     * @param \stdClass $assign Assignment.
     * @param \stdClass $submission Submission.
     * @param \context_module $context Context.
     * @return array Result.
     */
    private function grade(\stdClass $assign, \stdClass $submission, \context_module $context): array {
        return (new grading_service())->grade_submission($assign, $submission, $context);
    }

    /**
     * Normalise through the code under test.
     *
     * @param mixed $value Raw value.
     * @return float
     */
    private function normalize($value): float {
        return grading_service::normalize_confidence($value);
    }

    /**
     * Load lib.php.
     */
    public static function setUpBeforeClass(): void {
        global $CFG;
        parent::setUpBeforeClass();
        require_once($CFG->dirroot . '/mod/airagassign/lib.php');
    }

    /**
     * Create a material with the given status and file rows.
     *
     * @param int $courseid Course.
     * @param string $name Name.
     * @param string|null $status Status (null keeps the real default 'queued').
     * @param array $files filename => vectorized flag.
     * @return \stdClass
     */
    private function material(int $courseid, string $name, ?string $status, array $files): \stdClass {
        global $DB;
        $record = ['course' => $courseid, 'name' => $name];
        if ($status !== null) {
            $record['vectorize_status'] = $status;
        }
        $material = $this->getDataGenerator()->create_module('airagmaterial', $record);
        foreach ($files as $filename => $vectorized) {
            $DB->insert_record('airagmaterial_files', (object)[
                'materialid' => $material->id, 'filename' => $filename, 'filesize' => 1,
                'vectorized' => $vectorized, 'timecreated' => time(),
            ]);
        }
        return $material;
    }

    /**
     * Create an essay assignment with a submission.
     *
     * @param array $fields Assignment fields.
     * @param string $status Submission status.
     * @return array [assign record from DB, submission, context]
     */
    private function essay(array $fields, string $status = 'submitted'): array {
        global $DB;
        $assign = $this->getDataGenerator()->create_module('airagassign', $fields);
        $student = $this->getDataGenerator()->create_user();
        $submission = $this->getDataGenerator()->get_plugin_generator('mod_airagassign')
            ->create_submission($assign, $student->id, 'My essay text', $status);
        return [
            $DB->get_record('airagassign', ['id' => $assign->id], '*', MUST_EXIST),
            $DB->get_record('airagassign_submissions', ['id' => $submission->id], '*', MUST_EXIST),
            \context_module::instance($assign->cmid),
        ];
    }

    /**
     * Essay mode posts the scoped payload and stores the AI suggestion.
     */
    public function test_essay_success_stores_suggestion(): void {
        global $DB;
        $this->resetAfterTest();
        $course = $this->getDataGenerator()->create_course();
        $week1 = $this->material($course->id, 'Week 1', 'completed', ['w1.pdf' => 1]);
        [$assign, $submission, $context] = $this->essay([
            'course' => $course->id, 'maximumgrade' => 80, 'essayprompt' => 'Explain photosynthesis.',
            'criterionname' => ['Accuracy'], 'criteriondesc' => ['Correct facts'], 'criterionmaxscore' => [50],
            'materials' => [$week1->id],
        ]);
        $this->queue([[200, ['success' => true, 'score' => 42.456, 'feedback' => 'Good', 'confidence' => 1.7]]]);

        $result = $this->grade($assign, $submission, $context);

        $this->assertSame(['success' => true, 'ai_grade' => 42.46, 'feedback' => 'Good'], $result);
        $this->assertSame([120], $this->timeouts);
        $requests = $this->requests();
        $this->assertCount(1, $requests);
        $this->assertSame('POST', $requests[0]['method']);
        $this->assertSame('/assign/answer', $requests[0]['path']);
        $this->assertMatchesRegularExpression('/^[0-9a-f]{32}$/', $requests[0]['headers']['x-request-id']);
        $this->assertSame('Bearer k', $requests[0]['headers']['authorization']);
        $this->assertSame([
            'course_id' => (string)$course->id,
            'question' => 'Explain photosynthesis.',
            'essay' => 'My essay text',
            'rubric' => ['Accuracy' => ['description' => 'Correct facts', 'max_score' => 50]],
            'maximum_grade' => 80,
            'assignment_id' => (string)$assign->id,
            'source_filter' => ['w1.pdf'],
        ], $requests[0]['json']);

        $stored = $DB->get_record('airagassign_submissions', ['id' => $submission->id]);
        $this->assertSame('ai_suggested', $stored->status);
        $this->assertEquals(42.46, $stored->ai_grade);
        $this->assertSame('Good', $stored->ai_feedback);
        $this->assertEquals(1.0, $stored->confidence);
        $this->assertNull($stored->grading_error);
        $this->assertNull($stored->grading_requestid);
        $this->assertGreaterThan(0, (int)$stored->timegraded);
        $answer = $DB->get_record('airagassign_answers', ['submissionid' => $submission->id]);
        $this->assertEquals(42.46, $answer->ai_score);
        $this->assertSame('Good', $answer->ai_feedback);
        $this->assertNull($answer->score ?? null);
    }

    /**
     * Without criteria or links the rubric is sent as an empty JSON object and no filter is sent.
     */
    public function test_simple_rubric_sends_empty_object(): void {
        $this->resetAfterTest();
        $course = $this->getDataGenerator()->create_course();
        [$assign, $submission, $context] = $this->essay(['course' => $course->id, 'rubricmode' => 'simple']);
        $this->queue([[200, ['score' => 5, 'feedback' => 'ok', 'confidence' => 0.5]]]);

        $this->assertTrue($this->grade($assign, $submission, $context)['success']);
        $requests = $this->requests();
        $this->assertStringContainsString('"rubric":{}', $requests[0]['body']);
        $this->assertArrayNotHasKey('source_filter', $requests[0]['json']);
    }

    /**
     * An HTTP 500 marks the submission grading_failed with the error and request ID (via the adhoc task).
     */
    public function test_http_500_marks_grading_failed(): void {
        global $DB;
        $this->resetAfterTest();
        $course = $this->getDataGenerator()->create_course();
        [, $submission] = $this->essay(['course' => $course->id], 'grading');
        $this->queue([[500, ['detail' => 'boom']]]);

        $task = new \mod_airagassign\task\grade_submission();
        $task->set_custom_data(['submissionid' => $submission->id]);
        $this->expectOutputRegex('/Grading FAILED for submission \d+: HTTP 500: boom \[request ID: [0-9a-f]{32}\]/');
        $task->execute();

        $stored = $DB->get_record('airagassign_submissions', ['id' => $submission->id]);
        $this->assertSame('grading_failed', $stored->status);
        $this->assertSame('HTTP 500: boom', $stored->grading_error);
        $this->assertSame($this->requests()[0]['headers']['x-request-id'], $stored->grading_requestid);
        $this->assertEquals(0, $stored->grading_started_at);
    }

    /**
     * A 200 response with success=false reports the server's error message.
     */
    public function test_success_false_body(): void {
        $this->resetAfterTest();
        $course = $this->getDataGenerator()->create_course();
        [$assign, $submission, $context] = $this->essay(['course' => $course->id]);
        $this->queue([[200, ['success' => false, 'error' => 'LLM down', 'message' => 'ignored']]]);

        $result = $this->grade($assign, $submission, $context);
        $this->assertFalse($result['success']);
        $this->assertSame('LLM down', $result['error']);
        $this->assertMatchesRegularExpression('/^[0-9a-f]{32}$/', $result['requestid']);
    }

    /**
     * A network failure is reported as a connection error.
     */
    public function test_connection_error(): void {
        $this->resetAfterTest();
        $course = $this->getDataGenerator()->create_course();
        [$assign, $submission, $context] = $this->essay(['course' => $course->id]);
        $this->queue_connection_error();

        $result = $this->grade($assign, $submission, $context);
        $this->assertFalse($result['success']);
        $this->assertStringStartsWith('Connection error: ', $result['error']);
    }

    /**
     * Any unready linked material blocks grading before any HTTP request.
     */
    public function test_unready_material_blocks_grading(): void {
        $this->resetAfterTest();
        $course = $this->getDataGenerator()->create_course();
        $week1 = $this->material($course->id, 'Week 1', 'completed', ['w1.pdf' => 1]);
        $week2 = $this->material($course->id, 'Week 2', null, ['w2.pdf' => 0]);
        [$assign, $submission, $context] = $this->essay([
            'course' => $course->id, 'materials' => [$week1->id, $week2->id],
        ]);
        $this->queue([]);

        $result = $this->grade($assign, $submission, $context);

        $this->assertSame([
            'success' => false,
            'error' => get_string('linkedmaterials_not_ready', 'airagassign', 'Week 2 (Queued for vectorization)'),
        ], $result);
        $this->assertSame([], $this->requests());
    }

    /**
     * Linked materials without any vectorized file block grading.
     */
    public function test_no_vectorized_files_blocks_grading(): void {
        $this->resetAfterTest();
        $course = $this->getDataGenerator()->create_course();
        $week1 = $this->material($course->id, 'Week 1', 'completed', ['w1.pdf' => 0]);
        [$assign, $submission, $context] = $this->essay(['course' => $course->id, 'materials' => [$week1->id]]);
        $this->queue([]);

        $this->assertSame([
            'success' => false,
            'error' => get_string('linkedmaterials_no_vectorized_files', 'airagassign'),
        ], $this->grade($assign, $submission, $context));
        $this->assertSame([], $this->requests());
    }

    /**
     * Moodle rubric mode without a rubric definition refuses to grade.
     */
    public function test_moodle_rubric_not_configured(): void {
        $this->resetAfterTest();
        $course = $this->getDataGenerator()->create_course();
        [$assign, $submission, $context] = $this->essay(['course' => $course->id, 'rubricmode' => 'moodle']);
        $this->queue([]);

        $this->assertSame([
            'success' => false,
            'error' => get_string('moodlerubric_not_configured', 'airagassign'),
        ], $this->grade($assign, $submission, $context));
        $this->assertSame([], $this->requests());
    }

    /**
     * Create a two-question quiz with answers.
     *
     * @return array [assign, submission, context, course]
     */
    private function quiz(): array {
        global $DB;
        $course = $this->getDataGenerator()->create_course();
        $assign = $this->getDataGenerator()->create_module('airagassign', [
            'course' => $course->id, 'assignmode' => 'quiz', 'maximumgrade' => 10,
            'questions' => ['Q one?', 'Q two?'],
        ]);
        $student = $this->getDataGenerator()->create_user();
        $submissionid = $DB->insert_record('airagassign_submissions', (object)[
            'assignid' => $assign->id, 'userid' => $student->id, 'status' => 'grading',
            'grading_started_at' => time(), 'timecreated' => time(), 'timegraded' => 0,
        ]);
        foreach ($DB->get_records('airagassign_questions', ['assignid' => $assign->id], 'sortorder ASC') as $q) {
            $DB->insert_record('airagassign_answers', (object)[
                'submissionid' => $submissionid, 'questionid' => $q->id,
                'answertext' => 'Answer to ' . $q->questiontext, 'timecreated' => time(),
            ]);
        }
        return [
            $DB->get_record('airagassign', ['id' => $assign->id], '*', MUST_EXIST),
            $DB->get_record('airagassign_submissions', ['id' => $submissionid], '*', MUST_EXIST),
            \context_module::instance($assign->cmid),
            $course,
        ];
    }

    /**
     * Quiz mode grades each question and keeps the least certain confidence.
     */
    public function test_quiz_mode(): void {
        global $DB;
        $this->resetAfterTest();
        [$assign, $submission, $context] = $this->quiz();
        $this->queue([
            [200, ['score' => 3, 'feedback' => 'f1', 'confidence' => 0.9]],
            [200, ['score' => 4.5, 'feedback' => 'f2', 'confidence' => 0.4]],
        ]);

        $result = $this->grade($assign, $submission, $context);

        $this->assertSame(['success' => true, 'ai_grade' => 7.5, 'feedback' => "Q1: f1\n\nQ2: f2", 'errors' => []], $result);
        $requests = $this->requests();
        $this->assertCount(2, $requests);
        $this->assertSame('Q one?', $requests[0]['json']['question']);
        $this->assertSame('Answer to Q two?', $requests[1]['json']['essay']);
        $this->assertEquals(5, $requests[0]['json']['maximum_grade']);
        $stored = $DB->get_record('airagassign_submissions', ['id' => $submission->id]);
        $this->assertSame('ai_suggested', $stored->status);
        $this->assertEquals(7.5, $stored->ai_grade);
        $this->assertEquals(0.4, $stored->confidence);
        $this->assertEquals(0, $stored->grading_started_at);
    }

    /**
     * A failing question fails the whole quiz but keeps the other answers' AI scores.
     */
    public function test_quiz_partial_failure(): void {
        global $DB;
        $this->resetAfterTest();
        [$assign, $submission, $context] = $this->quiz();
        $this->queue([
            [200, ['score' => 3, 'feedback' => 'f1', 'confidence' => 0.9]],
            [500, ['detail' => 'nope']],
        ]);

        $result = $this->grade($assign, $submission, $context);

        $this->assertFalse($result['success']);
        $this->assertSame('Q2: HTTP 500: nope', $result['error']);
        $this->assertSame($this->requests()[1]['headers']['x-request-id'], $result['requestid']);
        $this->assertSame('grading', $DB->get_field('airagassign_submissions', 'status', ['id' => $submission->id]));
        $scores = $DB->get_fieldset_select('airagassign_answers', 'ai_score', 'submissionid = ? ORDER BY id', [$submission->id]);
        $this->assertEquals([3, null], $scores);
    }

    /**
     * Confidence values are clamped to 0..1 and non-numeric values become 0.
     *
     * @dataProvider confidence_provider
     * @param mixed $input Raw value.
     * @param float $expected Expected value.
     */
    public function test_normalize_confidence($input, float $expected): void {
        $this->assertSame($expected, $this->normalize($input));
    }

    /**
     * Confidence cases.
     *
     * @return array
     */
    public static function confidence_provider(): array {
        return [
            'in range' => [0.42, 0.42],
            'numeric string' => ['0.4', 0.4],
            'above' => [1.5, 1.0],
            'below' => [-3, 0.0],
            'text' => ['abc', 0.0],
            'null' => [null, 0.0],
            'nan' => [NAN, 0.0],
            'inf' => [INF, 0.0],
        ];
    }
}
