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
use GuzzleHttp\Handler\MockHandler;
use GuzzleHttp\HandlerStack;
use GuzzleHttp\Middleware;
use GuzzleHttp\Psr7\Response;
use mod_airagmaterial\local\http_factory;

/**
 * Characterization tests for the linked-material retrieval scope.
 *
 * @package    mod_airagassign
 * @category   test
 * @copyright  2026 RAGrader
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 * @covers     \mod_airagassign\local\material_scope
 */
final class material_scope_test extends \advanced_testcase {
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
     * @param array $responses List of [status, body array].
     */
    private function queue(array $responses): void {
        set_config('serverurl', 'http://rag.test', 'mod_airagassign');
        set_config('apikey', '', 'mod_airagassign');
        $this->mock_http(array_map(fn($r) => new Response($r[0], [], json_encode($r[1])), $responses));
    }

    /**
     * Requests received: method, path and form fields (file parts as field => filename).
     *
     * @return array
     */
    private function requests(): array {
        $out = [];
        foreach ($this->history as $entry) {
            $request = $entry['request'];
            $body = (string)$request->getBody();
            $form = [];
            if (str_starts_with($request->getHeaderLine('Content-Type'), 'multipart/form-data')) {
                preg_match_all('/name="([^"]+)"(?:; filename="([^"]+)")?.*?\r\n\r\n(.*?)\r\n--/s', $body, $parts, PREG_SET_ORDER);
                foreach ($parts as $part) {
                    $form[$part[1]] = $part[2] !== '' ? $part[2] : $part[3];
                }
                ksort($form);
            } else {
                parse_str($body, $form);
            }
            $out[] = ['method' => $request->getMethod(), 'path' => $request->getUri()->getPath(), 'form' => $form];
        }
        return $out;
    }

    /**
     * Delete through the code under test.
     *
     * @param int $courseid Course.
     * @param string $filename File.
     * @param int $assignid Assignment.
     * @return bool
     */
    private function delete(int $courseid, string $filename, int $assignid): bool {
        return material_scope::delete_manual_file_vectors($courseid, $filename, $assignid);
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
     * Create a course with a completed material (w1.pdf vectorized), a queued one and an assignment linking both.
     *
     * @return array [assign, context, week1, week2]
     */
    private function setup_scope(): array {
        global $DB;
        $course = $this->getDataGenerator()->create_course();
        $week1 = $this->getDataGenerator()->create_module('airagmaterial', [
            'course' => $course->id, 'name' => 'Week 1', 'vectorize_status' => 'completed',
        ]);
        $week2 = $this->getDataGenerator()->create_module('airagmaterial', [
            'course' => $course->id, 'name' => 'Week 2',
        ]);
        foreach ([['w1.pdf', 1], ['w1-draft.pdf', 0]] as [$filename, $vectorized]) {
            $DB->insert_record('airagmaterial_files', (object)[
                'materialid' => $week1->id, 'filename' => $filename, 'filesize' => 10,
                'vectorized' => $vectorized, 'timecreated' => time(),
            ]);
        }
        $DB->insert_record('airagmaterial_files', (object)[
            'materialid' => $week2->id, 'filename' => 'w2.pdf', 'filesize' => 10,
            'vectorized' => 1, 'timecreated' => time(),
        ]);
        $assign = $this->getDataGenerator()->create_module('airagassign', [
            'course' => $course->id, 'materials' => [$week1->id, $week2->id],
        ]);
        return [$assign, \context_module::instance($assign->cmid), $week1, $week2];
    }

    /**
     * Only the queued material is unready; only vectorized files of completed materials are in scope.
     */
    public function test_scope_with_one_unready_material(): void {
        $this->resetAfterTest();
        [$assign, $context, , $week2] = $this->setup_scope();

        $unready = material_scope::unready_materials((int)$assign->id);
        $this->assertCount(1, $unready);
        $this->assertEquals($week2->id, $unready[0]->id);
        $this->assertSame('Week 2', $unready[0]->name);
        $this->assertSame('queued', $unready[0]->vectorize_status);

        $this->assertSame(['w1.pdf'], material_scope::linked_filenames((int)$assign->id, $context->id));
        $this->assertSame('Week 2 (Queued for vectorization)', material_scope::describe_unready($unready, $context));
    }

    /**
     * Unknown or empty statuses are described as pending; unknown keys are shown raw.
     */
    public function test_describe_unready_fallbacks(): void {
        $this->resetAfterTest();
        $context = \context_system::instance();
        $materials = [
            (object)['id' => 1, 'name' => 'A', 'vectorize_status' => null],
            (object)['id' => 2, 'name' => 'B', 'vectorize_status' => 'weird'],
        ];
        $this->assertSame('A (Pending vectorization), B (weird)',
            material_scope::describe_unready($materials, $context));
    }

    /**
     * Manual reference files join the scope only once their current content is vectorized.
     */
    public function test_manual_file_in_scope(): void {
        global $DB;
        $this->resetAfterTest();
        [$assign, $context, $week1] = $this->setup_scope();
        $file = get_file_storage()->create_file_from_string([
            'contextid' => $context->id, 'component' => 'mod_airagassign', 'filearea' => 'manualfile',
            'itemid' => 0, 'filepath' => '/', 'filename' => 'key.txt',
        ], 'answer key');
        $this->assertSame(['key.txt' => $file->get_contenthash()], material_scope::manual_file_hashes($context->id));
        $this->assertSame(['w1.pdf'], material_scope::linked_filenames((int)$assign->id, $context->id));
        $this->assertSame(['airagmaterial:' . $week1->id], material_scope::owner_ids((int)$assign->id, $context->id));

        $DB->insert_record('airagassign_manualfiles', (object)['assignid' => $assign->id, 'filename' => 'key.txt',
            'contenthash' => $file->get_contenthash(), 'status' => 'completed', 'timemodified' => time()]);

        $this->assertSame(['w1.pdf', 'key.txt'], material_scope::linked_filenames((int)$assign->id, $context->id));
        $this->assertSame(['airagmaterial:' . $week1->id, 'airagassign:' . $assign->id],
            material_scope::owner_ids((int)$assign->id, $context->id));
    }

    /**
     * Unready manual files are described with their status label and error.
     */
    public function test_describe_unready_manualfiles(): void {
        $this->resetAfterTest();
        $files = [
            (object)['filename' => 'a.pdf', 'status' => 'queued', 'error_message' => ''],
            (object)['filename' => 'b.pdf', 'status' => 'failed', 'error_message' => 'HTTP 500: boom'],
        ];
        $this->assertSame('a.pdf (Queued for vectorization), b.pdf (Failed: HTTP 500: boom)',
            material_scope::describe_unready_manualfiles($files));
    }

    /**
     * Deleting manual-file vectors is scoped to the assignment owner id; only HTTP 200 is success.
     */
    public function test_delete_manual_file_vectors(): void {
        $this->resetAfterTest();
        $course = $this->getDataGenerator()->create_course();

        $this->queue([[200, ['success' => false, 'message' => 'no vectors found']], [500, ['detail' => 'x']]]);
        $this->assertTrue($this->delete($course->id, 'key.txt', 7));
        $this->assertSame([30], $this->timeouts);
        $this->assertSame([[
            'method' => 'DELETE',
            'path' => '/course/materials/file',
            'form' => ['course_id' => (string)$course->id, 'filename' => 'key.txt', 'material_id' => 'airagassign:7'],
        ]], $this->requests());

        $this->assertFalse($this->delete($course->id, 'key.txt', 7));
        $this->assertDebuggingCalled();
    }
}
