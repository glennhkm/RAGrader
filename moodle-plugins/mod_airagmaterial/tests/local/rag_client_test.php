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

namespace mod_airagmaterial\local;

use GuzzleHttp\Client;
use GuzzleHttp\Exception\ConnectException;
use GuzzleHttp\Handler\MockHandler;
use GuzzleHttp\HandlerStack;
use GuzzleHttp\Middleware;
use GuzzleHttp\Psr7\Request;
use GuzzleHttp\Psr7\Response;

/**
 * Tests for the RAG HTTP client.
 *
 * @package    mod_airagmaterial
 * @category   test
 * @copyright  2026 RAGrader
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 * @covers     \mod_airagmaterial\local\rag_client
 * @covers     \mod_airagmaterial\local\http_factory
 */
final class rag_client_test extends \advanced_testcase {
    /** @var array Request history. */
    private array $history = [];

    /**
     * Build a Guzzle client with mocked responses.
     *
     * @param array $queue Responses or exceptions.
     * @return Client
     */
    private function mock_http(array $queue): Client {
        $this->history = [];
        $stack = HandlerStack::create(new MockHandler($queue));
        $stack->push(Middleware::history($this->history));
        return new Client(['handler' => $stack]);
    }

    /**
     * Create a temp file with content.
     *
     * @return string Path.
     */
    private function temp_file(): string {
        $path = make_request_directory() . '/notes.txt';
        file_put_contents($path, 'hello vectors');
        return $path;
    }

    public function test_upload_sends_multipart_with_material_id(): void {
        $this->resetAfterTest();
        $http = $this->mock_http([new Response(200, [], json_encode(['success' => true, 'chunk_count' => 4]))]);
        $client = new rag_client('http://rag.test/', 'k', $http);

        $result = $client->upload_material(7, $this->temp_file(), 'orig name.txt', 'airagmaterial:3');

        $this->assertTrue($result['success']);
        $this->assertSame(200, $result['status']);
        $this->assertSame(4, $result['data']['chunk_count']);
        $this->assertCount(1, $this->history);
        $request = $this->history[0]['request'];
        $this->assertSame('POST', $request->getMethod());
        $this->assertSame('http://rag.test/course/materials/upload', (string)$request->getUri());
        $this->assertSame('Bearer k', $request->getHeaderLine('Authorization'));
        $body = (string)$request->getBody();
        $this->assertStringContainsString('name="course_id"', $body);
        $this->assertMatchesRegularExpression('/name="course_id"\r\n(?:[^\r]+\r\n)*\r\n7\r\n/', $body);
        $this->assertMatchesRegularExpression('/name="material_id"\r\n(?:[^\r]+\r\n)*\r\nairagmaterial:3\r\n/', $body);
        $this->assertStringContainsString('filename="orig name.txt"', $body);
        $this->assertStringContainsString('hello vectors', $body);
        $this->assertStringContainsString('name="course_name"', $body);
    }

    public function test_material_id_is_omitted_when_null(): void {
        $this->resetAfterTest();
        $http = $this->mock_http([new Response(200, [], '{"success": true}')]);
        $client = new rag_client('http://rag.test', '', $http);

        $client->upload_material(7, $this->temp_file(), 'notes.txt');

        $this->assertStringNotContainsString('material_id', (string)$this->history[0]['request']->getBody());
    }

    public function test_http_error_returns_failure_with_status(): void {
        $this->resetAfterTest();
        $http = $this->mock_http([new Response(503, [], json_encode(['detail' => 'Vector store down']))]);
        $client = new rag_client('http://rag.test', 'k', $http);

        $result = $client->upload_material(7, $this->temp_file(), 'notes.txt');

        $this->assertFalse($result['success']);
        $this->assertSame(503, $result['status']);
        $this->assertStringContainsString('Vector store down', $result['error']);
    }

    public function test_connection_error_never_throws(): void {
        $this->resetAfterTest();
        $http = $this->mock_http([new ConnectException('refused', new Request('POST', 'http://rag.test'))]);
        $client = new rag_client('http://rag.test', 'k', $http);

        $result = $client->upload_material(7, $this->temp_file(), 'notes.txt');

        $this->assertFalse($result['success']);
        $this->assertSame(0, $result['status']);
        $this->assertStringContainsString('refused', $result['error']);
    }

    public function test_no_auth_header_without_api_key(): void {
        $this->resetAfterTest();
        $http = $this->mock_http([new Response(200, [], '{"success": true}')]);
        $client = new rag_client('http://rag.test', '', $http);

        $client->delete_file(7, 'notes.txt');

        $this->assertFalse($this->history[0]['request']->hasHeader('Authorization'));
    }

    public function test_delete_file_sends_form_body(): void {
        $this->resetAfterTest();
        $http = $this->mock_http([new Response(200, [], '{"success": true}')]);
        $client = new rag_client('http://rag.test', 'k', $http);

        $result = $client->delete_file(7, 'notes.txt', 'airagmaterial:3');

        $this->assertTrue($result['success']);
        $request = $this->history[0]['request'];
        $this->assertSame('DELETE', $request->getMethod());
        $this->assertSame('http://rag.test/course/materials/file', (string)$request->getUri());
        parse_str((string)$request->getBody(), $form);
        $this->assertSame(['course_id' => '7', 'filename' => 'notes.txt', 'material_id' => 'airagmaterial:3'], $form);
    }

    public function test_grade_sends_json_with_request_id(): void {
        $this->resetAfterTest();
        $http = $this->mock_http([new Response(200, [], json_encode(['score' => 80]))]);
        $client = new rag_client('http://rag.test', 'k', $http);

        $result = $client->grade(['answer' => 'x'], 'req-1');

        $this->assertTrue($result['success']);
        $this->assertSame(80, $result['data']['score']);
        $request = $this->history[0]['request'];
        $this->assertSame('http://rag.test/assign/answer', (string)$request->getUri());
        $this->assertSame('req-1', $request->getHeaderLine('X-Request-ID'));
        $this->assertSame(['answer' => 'x'], json_decode((string)$request->getBody(), true));
    }

    public function test_server_reported_failure(): void {
        $this->resetAfterTest();
        $http = $this->mock_http([new Response(200, [], json_encode(['success' => false, 'message' => 'bad file']))]);
        $client = new rag_client('http://rag.test', '', $http);

        $result = $client->upload_material(7, $this->temp_file(), 'notes.txt');

        $this->assertFalse($result['success']);
        $this->assertSame('bad file', $result['error']);
    }

    public function test_for_component_reads_settings_and_uses_factory(): void {
        $this->resetAfterTest();
        set_config('serverurl', 'http://configured.test', 'mod_airagmaterial');
        set_config('apikey', 'secret', 'mod_airagmaterial');
        $http = $this->mock_http([new Response(200, [], '{"success": true}')]);
        $factory = $this->createMock(http_factory::class);
        $factory->expects($this->once())->method('create')->with(300)->willReturn($http);
        \core\di::set(http_factory::class, $factory);

        rag_client::for_component('mod_airagmaterial')->delete_file(1, 'a.txt');

        $request = $this->history[0]['request'];
        $this->assertSame('http://configured.test/course/materials/file', (string)$request->getUri());
        $this->assertSame('Bearer secret', $request->getHeaderLine('Authorization'));
    }

    public function test_lib_functions_go_through_the_client(): void {
        global $CFG;
        require_once($CFG->dirroot . '/mod/airagmaterial/lib.php');
        $this->resetAfterTest();
        set_config('serverurl', 'http://configured.test', 'mod_airagmaterial');
        $http = $this->mock_http([
            new Response(200, [], json_encode(['success' => true, 'chunk_count' => 2, 'documents_loaded' => 1])),
            new Response(200, [], '{"success": true}'),
            new Response(500, [], 'boom'),
        ]);
        $factory = $this->createMock(http_factory::class);
        $factory->method('create')->willReturn($http);
        \core\di::set(http_factory::class, $factory);

        $sent = airagmaterial_send_file_to_rag('http://configured.test', $this->temp_file(), 'notes.txt', 5);
        $this->assertTrue($sent['success']);
        $this->assertSame(2, $sent['chunks_created']);

        $this->assertTrue(airagmaterial_delete_file_vectors(5, 'notes.txt'));
        $this->assertFalse(airagmaterial_delete_file_vectors(5, 'notes.txt'));
        $this->assertDebuggingCalled();
        $this->assertCount(3, $this->history);
    }

    public function test_delete_vectors_treats_http_200_as_success(): void {
        global $CFG;
        require_once($CFG->dirroot . '/mod/airagmaterial/lib.php');
        $this->resetAfterTest();
        $http = $this->mock_http([
            new Response(200, [], json_encode(['success' => false, 'message' => 'No vectors found or failed to delete'])),
            new Response(200, [], ''),
            new Response(404, [], '{"detail": "nope"}'),
        ]);
        $factory = $this->createMock(http_factory::class);
        $factory->method('create')->willReturn($http);
        \core\di::set(http_factory::class, $factory);

        $this->assertTrue(airagmaterial_delete_file_vectors(5, 'notes.txt'));
        $this->assertTrue(airagmaterial_delete_file_vectors(5, 'notes.txt'));
        $this->assertDebuggingNotCalled();
        $this->assertFalse(airagmaterial_delete_file_vectors(5, 'notes.txt'));
        $this->assertDebuggingCalled();
    }

    public function test_default_factory_builds_a_client(): void {
        $this->assertInstanceOf(\GuzzleHttp\ClientInterface::class, (new http_factory())->create(5));
    }
}
