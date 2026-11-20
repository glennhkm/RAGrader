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

namespace mod_airagassign;

use GuzzleHttp\Client;
use GuzzleHttp\Handler\MockHandler;
use GuzzleHttp\HandlerStack;
use GuzzleHttp\Middleware;
use GuzzleHttp\Psr7\Response;
use mod_airagassign\local\material_scope;
use mod_airagassign\task\vectorize_manualfile;
use mod_airagmaterial\local\http_factory;

/**
 * Tests for manual reference file vectorization tracking and owner scoping.
 *
 * @package    mod_airagassign
 * @category   test
 * @copyright  2026 RAGrader
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 * @covers     \mod_airagassign\task\vectorize_manualfile
 * @covers     \mod_airagassign\local\material_scope
 * @covers     ::airagassign_add_instance
 * @covers     ::airagassign_update_instance
 * @covers     ::airagassign_delete_instance
 * @covers     ::xmldb_airagassign_upgrade
 * @covers     \restore_airagassign_activity_structure_step
 */
final class manualfile_test extends \advanced_testcase {
    /** @var string Task class name as stored in {task_adhoc}. */
    private const TASK = '\\mod_airagassign\\task\\vectorize_manualfile';

    /** @var array Guzzle request history. */
    private array $history = [];

    /**
     * Load lib.php.
     */
    public static function setUpBeforeClass(): void {
        global $CFG;
        parent::setUpBeforeClass();
        require_once($CFG->dirroot . '/mod/airagassign/lib.php');
    }

    /**
     * Route every RAG client through a mocked Guzzle handler.
     *
     * @param array $responses List of [status, body array].
     */
    private function queue(array $responses): void {
        set_config('serverurl', 'http://rag.test', 'mod_airagassign');
        set_config('apikey', '', 'mod_airagassign');
        $this->history = [];
        $stack = HandlerStack::create(new MockHandler(array_map(
            fn($r) => new Response($r[0], [], json_encode($r[1])), $responses)));
        $stack->push(Middleware::history($this->history));
        $http = new Client(['handler' => $stack]);
        $factory = $this->createMock(http_factory::class);
        $factory->method('create')->willReturn($http);
        \core\di::set(http_factory::class, $factory);
    }

    /**
     * Fail on any attempt to create an HTTP client.
     */
    private function forbid_http(): void {
        $factory = $this->createMock(http_factory::class);
        $factory->expects($this->never())->method('create');
        \core\di::set(http_factory::class, $factory);
    }

    /**
     * Requests received: method, path, form fields and raw body.
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
                preg_match_all('/name="([^"]+)"(?:; filename="([^"]+)")?.*?\r\n\r\n(.*?)\r\n--/s', $body, $parts,
                    PREG_SET_ORDER);
                foreach ($parts as $part) {
                    $form[$part[1]] = $part[2] !== '' ? $part[2] : $part[3];
                }
                ksort($form);
            } else {
                parse_str($body, $form);
            }
            $out[] = ['method' => $request->getMethod(), 'path' => $request->getUri()->getPath(),
                'form' => $form, 'body' => $body];
        }
        return $out;
    }

    /**
     * Store a manual reference file directly in the file area.
     *
     * @param int $contextid Module context.
     * @param string $content File content.
     * @param string $filename File name.
     * @return \stored_file
     */
    private function put_file(int $contextid, string $content, string $filename = 'key.txt'): \stored_file {
        $fs = get_file_storage();
        $fs->delete_area_files($contextid, 'mod_airagassign', 'manualfile');
        return $fs->create_file_from_string([
            'contextid' => $contextid, 'component' => 'mod_airagassign', 'filearea' => 'manualfile',
            'itemid' => 0, 'filepath' => '/', 'filename' => $filename,
        ], $content);
    }

    /**
     * Create an assignment (no manual file) and return it with its context.
     *
     * @return array [course, assign, context]
     */
    private function assignment(): array {
        $course = $this->getDataGenerator()->create_course();
        $assign = $this->getDataGenerator()->create_module('airagassign', ['course' => $course->id]);
        return [$course, $assign, \context_module::instance($assign->cmid)];
    }

    /**
     * Run the vectorization task for an assignment, returning its output.
     *
     * @param int $assignid Assignment ID.
     * @return string mtrace output.
     */
    private function run_task(int $assignid): string {
        $task = new vectorize_manualfile();
        $task->set_custom_data(['assignid' => $assignid]);
        ob_start();
        try {
            $task->execute();
        } finally {
            $output = ob_get_clean();
        }
        return $output;
    }

    /**
     * Manual file rows of an assignment keyed by filename.
     *
     * @param int $assignid Assignment ID.
     * @return array
     */
    private function rows(int $assignid): array {
        global $DB;
        $rows = [];
        foreach ($DB->get_records('airagassign_manualfiles', ['assignid' => $assignid]) as $row) {
            $rows[$row->filename] = $row;
        }
        return $rows;
    }

    /**
     * The owner id format matches the backend's ^[a-z_]+:[0-9]+$ contract.
     */
    public function test_owner_id(): void {
        $this->assertSame('airagassign:42', airagassign_manualfile_owner(42));
    }

    /**
     * Saving a new assignment with a manual file queues the task and makes no HTTP request.
     */
    public function test_save_queues_instead_of_uploading(): void {
        global $DB, $USER;
        $this->resetAfterTest();
        $this->setAdminUser();
        $DB->delete_records('task_adhoc');
        $this->forbid_http();

        $draftid = file_get_unused_draft_itemid();
        get_file_storage()->create_file_from_string([
            'contextid' => \context_user::instance($USER->id)->id, 'component' => 'user', 'filearea' => 'draft',
            'itemid' => $draftid, 'filepath' => '/', 'filename' => 'key.txt',
        ], 'answer key');
        $course = $this->getDataGenerator()->create_course();
        $assign = $this->getDataGenerator()->create_module('airagassign', [
            'course' => $course->id, 'manualfile' => $draftid,
        ]);

        $this->assertSame(1, $DB->count_records('task_adhoc', ['classname' => self::TASK]));
        $rows = $this->rows((int)$assign->id);
        $this->assertSame(['key.txt'], array_keys($rows));
        $this->assertSame('queued', $rows['key.txt']->status);
    }

    /**
     * The task uploads the file as it is when it runs and records that file's hash.
     */
    public function test_stale_task_does_not_mark_new_content(): void {
        $this->resetAfterTest();
        [$course, $assign, $context] = $this->assignment();
        $old = $this->put_file($context->id, 'old answer key');
        material_scope::queue_manualfile_vectorization((int)$assign->id, (int)$context->id);
        $this->assertSame($old->get_contenthash(), $this->rows((int)$assign->id)['key.txt']->contenthash);

        $new = $this->put_file($context->id, 'new answer key');
        $this->queue([[200, ['success' => true, 'chunk_count' => 1]]]);
        $this->run_task((int)$assign->id);

        $row = $this->rows((int)$assign->id)['key.txt'];
        $this->assertSame('completed', $row->status);
        $this->assertSame($new->get_contenthash(), $row->contenthash);
        $requests = $this->requests();
        $this->assertCount(1, $requests);
        $this->assertSame('/course/materials/upload', $requests[0]['path']);
        $this->assertSame([
            'course_id' => (string)$course->id, 'course_name' => '', 'file' => 'key.txt',
            'material_id' => 'airagassign:' . $assign->id,
        ], $requests[0]['form']);
        $this->assertStringContainsString('new answer key', $requests[0]['body']);
        $this->assertStringNotContainsString('old answer key', $requests[0]['body']);
        $this->assertSame([], material_scope::unready_manualfiles((int)$assign->id, (int)$context->id));
    }

    /**
     * A failed upload marks the row failed with the error, and it is reported unready.
     */
    public function test_failed_upload_marks_row_failed(): void {
        $this->resetAfterTest();
        [, $assign, $context] = $this->assignment();
        $this->put_file($context->id, 'answer key');
        material_scope::queue_manualfile_vectorization((int)$assign->id, (int)$context->id);
        $this->queue([[500, ['detail' => 'disk full']]]);

        $output = $this->run_task((int)$assign->id);

        $row = $this->rows((int)$assign->id)['key.txt'];
        $this->assertSame('failed', $row->status);
        $this->assertStringStartsWith('HTTP 500: ', $row->error_message);
        $this->assertStringContainsString('disk full', $row->error_message);
        $this->assertStringContainsString('failed', $output);
        $unready = material_scope::unready_manualfiles((int)$assign->id, (int)$context->id);
        $this->assertCount(1, $unready);
        $this->assertSame('key.txt', $unready[0]->filename);
        $this->assertSame('failed', $unready[0]->status);
    }

    /**
     * A task whose assignment was deleted meanwhile exits without HTTP or exceptions.
     */
    public function test_task_for_deleted_assignment_exits_quietly(): void {
        global $DB;
        $this->resetAfterTest();
        [, $assign, $context] = $this->assignment();
        $this->put_file($context->id, 'answer key');
        material_scope::queue_manualfile_vectorization((int)$assign->id, (int)$context->id);
        $DB->delete_records('airagassign_manualfiles', ['assignid' => $assign->id]);
        $DB->delete_records('airagassign', ['id' => $assign->id]);
        $this->forbid_http();

        $output = $this->run_task((int)$assign->id);

        $this->assertStringContainsString('skipping', $output);
        $this->assertSame([], $this->rows((int)$assign->id));
    }

    /**
     * Missing rows and replaced content are unready; only completed, current files are ready.
     */
    public function test_unready_manualfiles_detects_missing_and_stale_rows(): void {
        global $DB;
        $this->resetAfterTest();
        [, $assign, $context] = $this->assignment();
        $file = $this->put_file($context->id, 'v1');

        $unready = material_scope::unready_manualfiles((int)$assign->id, (int)$context->id);
        $this->assertSame([['key.txt', 'pending']], array_map(fn($r) => [$r->filename, $r->status], $unready));

        $DB->insert_record('airagassign_manualfiles', (object)['assignid' => $assign->id, 'filename' => 'key.txt',
            'contenthash' => $file->get_contenthash(), 'status' => 'completed', 'timemodified' => time()]);
        $this->assertSame([], material_scope::unready_manualfiles((int)$assign->id, (int)$context->id));
        $this->assertSame(['airagassign:' . $assign->id],
            material_scope::owner_ids((int)$assign->id, (int)$context->id));

        $this->put_file($context->id, 'v2');
        $unready = material_scope::unready_manualfiles((int)$assign->id, (int)$context->id);
        $this->assertSame([['key.txt', 'pending']], array_map(fn($r) => [$r->filename, $r->status], $unready));
    }

    /**
     * The upgrade creates queued rows and one task per assignment with manual files, without HTTP.
     */
    public function test_upgrade_queues_existing_manualfiles(): void {
        global $CFG, $DB;
        require_once($CFG->libdir . '/upgradelib.php');
        require_once($CFG->dirroot . '/mod/airagassign/db/upgrade.php');
        $this->resetAfterTest();
        [, $withfile, $context] = $this->assignment();
        $this->put_file($context->id, 'answer key');
        $this->assignment();
        $DB->delete_records('airagassign_manualfiles');
        $DB->delete_records('task_adhoc');
        $this->forbid_http();
        set_config('version', 2026112000, 'mod_airagassign');

        $this->assertTrue(xmldb_airagassign_upgrade(2026112000));

        $rows = $DB->get_records('airagassign_manualfiles');
        $this->assertCount(1, $rows);
        $row = reset($rows);
        $this->assertEquals($withfile->id, $row->assignid);
        $this->assertSame('queued', $row->status);
        $this->assertSame(1, $DB->count_records('task_adhoc', ['classname' => self::TASK]));
    }

    /**
     * Removing the manual file deletes its owner-scoped vectors and its status row.
     */
    public function test_update_removing_file_deletes_owned_vectors(): void {
        global $DB;
        $this->resetAfterTest();
        $this->setAdminUser();
        [$course, $assign, $context] = $this->assignment();
        $this->put_file($context->id, 'answer key');
        material_scope::queue_manualfile_vectorization((int)$assign->id, (int)$context->id);
        $DB->delete_records('task_adhoc');
        $this->queue([[200, ['success' => true]]]);

        $data = $DB->get_record('airagassign', ['id' => $assign->id]);
        $data->instance = $assign->id;
        $data->coursemodule = $assign->cmid;
        $data->manualfile = file_get_unused_draft_itemid();
        $this->assertTrue(airagassign_update_instance($data));

        $this->assertSame([[
            'method' => 'DELETE', 'path' => '/course/materials/file',
            'form' => ['course_id' => (string)$course->id, 'filename' => 'key.txt',
                'material_id' => 'airagassign:' . $assign->id],
        ]], array_map(fn($r) => array_diff_key($r, ['body' => 1]), $this->requests()));
        $this->assertSame([], $this->rows((int)$assign->id));
        $this->assertSame(0, $DB->count_records('task_adhoc', ['classname' => self::TASK]));
    }

    /**
     * Deleting the assignment deletes the manual file's owner-scoped vectors and status rows.
     */
    public function test_delete_instance_deletes_owned_vectors(): void {
        $this->resetAfterTest();
        [$course, $assign, $context] = $this->assignment();
        $this->put_file($context->id, 'answer key');
        material_scope::queue_manualfile_vectorization((int)$assign->id, (int)$context->id);
        $this->queue([[200, ['success' => true]]]);

        $this->assertTrue(airagassign_delete_instance((int)$assign->id));

        $this->assertSame([[
            'method' => 'DELETE', 'path' => '/course/materials/file',
            'form' => ['course_id' => (string)$course->id, 'filename' => 'key.txt',
                'material_id' => 'airagassign:' . $assign->id],
        ]], array_map(fn($r) => array_diff_key($r, ['body' => 1]), $this->requests()));
        $this->assertSame([], $this->rows((int)$assign->id));
    }

    /**
     * A restored assignment gets queued rows for its manual file and a queued task.
     */
    public function test_restore_queues_manualfiles(): void {
        global $CFG, $DB;
        require_once($CFG->dirroot . '/course/lib.php');
        $this->resetAfterTest();
        $this->setAdminUser();
        [$course, $assign, $context] = $this->assignment();
        $this->put_file($context->id, 'answer key');
        $DB->delete_records('task_adhoc');
        $this->forbid_http();

        $newcm = duplicate_module($course, get_fast_modinfo($course)->get_cm($assign->cmid));
        $newid = (int)$newcm->instance;
        $this->assertNotEquals((int)$assign->id, $newid);
        $rows = $this->rows($newid);
        $this->assertSame(['key.txt'], array_keys($rows));
        $this->assertSame('queued', $rows['key.txt']->status);
        $this->assertSame(1, $DB->count_records('task_adhoc', ['classname' => self::TASK]));
    }
}
