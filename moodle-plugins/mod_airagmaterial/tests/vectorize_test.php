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

namespace mod_airagmaterial;

use GuzzleHttp\Client;
use GuzzleHttp\Handler\MockHandler;
use GuzzleHttp\HandlerStack;
use GuzzleHttp\Middleware;
use GuzzleHttp\Psr7\Response;
use mod_airagmaterial\local\http_factory;

/**
 * Tests for owner-scoped vectorization and the post-upgrade migration.
 *
 * @package    mod_airagmaterial
 * @category   test
 * @copyright  2026 RAGrader
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 * @covers     ::airagmaterial_vectorize_files
 * @covers     ::airagmaterial_material_owner
 * @covers     ::airagmaterial_queue_owner_migration
 * @covers     \mod_airagmaterial\task\vectorize_material
 */
final class vectorize_test extends \advanced_testcase {
    /** @var array Request history. */
    private array $history = [];

    /**
     * Install a mocked HTTP client.
     *
     * @param array $queue Responses.
     */
    private function mock_http(array $queue): void {
        global $CFG;
        require_once($CFG->dirroot . '/mod/airagmaterial/lib.php');
        $this->history = [];
        $stack = HandlerStack::create(new MockHandler($queue));
        $stack->push(Middleware::history($this->history));
        $factory = $this->createMock(http_factory::class);
        $factory->method('create')->willReturn(new Client(['handler' => $stack]));
        \core\di::set(http_factory::class, $factory);
    }

    /**
     * Success response for an upload.
     *
     * @return Response
     */
    private function ok_upload(): Response {
        return new Response(200, [], json_encode(['success' => true, 'chunk_count' => 2, 'documents_loaded' => 1]));
    }

    public function test_vectorize_sends_material_owner(): void {
        global $DB;
        $this->resetAfterTest();
        $course = $this->getDataGenerator()->create_course();
        $gen = $this->getDataGenerator()->get_plugin_generator('mod_airagmaterial');
        $material = $gen->create_instance(['course' => $course->id]);
        $gen->create_file($material, 'a.txt', 'alpha');
        $gen->create_file($material, 'b.txt', 'beta');
        $this->mock_http([$this->ok_upload(), $this->ok_upload()]);

        $context = \context_module::instance($material->cmid);
        $result = airagmaterial_vectorize_files(
            $DB->get_record('airagmaterial', ['id' => $material->id]), $context);

        $this->assertTrue($result['success']);
        $this->assertCount(2, $this->history);
        foreach ($this->history as $entry) {
            $this->assertMatchesRegularExpression(
                '/name="material_id"\r\n(?:[^\r]+\r\n)*\r\nairagmaterial:' . $material->id . '\r\n/',
                (string)$entry['request']->getBody());
        }
        $this->assertSame('airagmaterial:' . $material->id, airagmaterial_material_owner((int)$material->id));
    }

    public function test_removed_file_is_deleted_with_owner(): void {
        global $DB;
        $this->resetAfterTest();
        $course = $this->getDataGenerator()->create_course();
        $gen = $this->getDataGenerator()->get_plugin_generator('mod_airagmaterial');
        $material = $gen->create_instance(['course' => $course->id]);
        $gen->create_file($material, 'keep.txt', 'keep');
        $DB->insert_record('airagmaterial_files', (object)[
            'materialid' => $material->id, 'filename' => 'gone.txt', 'filesize' => 1, 'mimetype' => 'text/plain',
            'contenthash' => 'x', 'vectorized' => 1, 'chunks_count' => 1, 'timecreated' => time(),
        ]);
        $this->mock_http([new Response(200, [], '{"success": true}'), $this->ok_upload()]);

        airagmaterial_vectorize_files($DB->get_record('airagmaterial', ['id' => $material->id]),
            \context_module::instance($material->cmid));

        $this->assertCount(2, $this->history);
        $delete = $this->history[0]['request'];
        $this->assertSame('DELETE', $delete->getMethod());
        $body = (string)$delete->getBody();
        parse_str($body, $form);
        $this->assertSame('gone.txt', $form['filename']);
        $this->assertSame('airagmaterial:' . $material->id, $form['material_id']);
    }

    public function test_task_for_deleted_material_exits_quietly(): void {
        global $DB;
        $this->resetAfterTest();
        $course = $this->getDataGenerator()->create_course();
        $gen = $this->getDataGenerator()->get_plugin_generator('mod_airagmaterial');
        $material = $gen->create_instance(['course' => $course->id]);
        $gen->create_file($material, 'a.txt', 'alpha');
        $contextid = \context_module::instance($material->cmid)->id;
        $this->mock_http([]);

        $task = new \mod_airagmaterial\task\vectorize_material();
        $task->set_custom_data(['materialid' => (int)$material->id, 'contextid' => (int)$contextid]);
        $DB->delete_records('airagmaterial', ['id' => $material->id]);

        ob_start();
        $task->execute();
        $output = ob_get_clean();

        $this->assertStringContainsString('not found', $output);
        $this->assertCount(0, $this->history);
    }

    public function test_queue_owner_migration_queues_without_http(): void {
        global $DB;
        $this->resetAfterTest();
        $course = $this->getDataGenerator()->create_course();
        $gen = $this->getDataGenerator()->get_plugin_generator('mod_airagmaterial');
        $m1 = $gen->create_instance(['course' => $course->id, 'vectorize_status' => 'completed']);
        $m2 = $gen->create_instance(['course' => $course->id, 'vectorize_status' => 'completed']);
        $m3 = $gen->create_instance(['course' => $course->id, 'vectorize_status' => 'completed']);
        $gen->create_file($m1, 'a.txt', 'alpha');
        $gen->create_file($m2, 'b.txt', 'beta');
        $DB->delete_records('task_adhoc');
        $this->mock_http([]);

        $this->assertSame(2, airagmaterial_queue_owner_migration());

        $this->assertSame('queued', $DB->get_field('airagmaterial', 'vectorize_status', ['id' => $m1->id]));
        $this->assertSame('queued', $DB->get_field('airagmaterial', 'vectorize_status', ['id' => $m2->id]));
        $this->assertSame('completed', $DB->get_field('airagmaterial', 'vectorize_status', ['id' => $m3->id]));
        $this->assertSame(2, $DB->count_records('task_adhoc'));
        $this->assertCount(0, $this->history);
    }
}
