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

use GuzzleHttp\ClientInterface;
use GuzzleHttp\Exception\GuzzleException;
use GuzzleHttp\Exception\RequestException;
use Psr\Http\Message\ResponseInterface;

/**
 * HTTP client for the RAGrader backend API.
 *
 * Every method returns ['success' => bool, 'error' => ?string, 'status' => int, 'data' => array]
 * and never throws for HTTP or network errors (status 0 means no HTTP response).
 *
 * The default client is built by {@see http_factory} with 'ignoresecurity' enabled.
 * Moodle's core SSRF filter would otherwise block internal/private hosts, but the
 * server URL is configured by an administrator (moodle/site:config) and a RAG
 * server on localhost or a private network is the normal deployment.
 *
 * @package    mod_airagmaterial
 * @copyright  2026 RAGrader
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */
final class rag_client {
    /** @var string Base URL without trailing slash. */
    private string $serverurl;

    /** @var string Bearer token ('' for none). */
    private string $apikey;

    /** @var ClientInterface HTTP client. */
    private ClientInterface $http;

    /**
     * Constructor.
     *
     * @param string $serverurl RAG server base URL.
     * @param string $apikey Optional bearer token.
     * @param ClientInterface|null $http Injected client; built via http_factory when null.
     * @param int $timeout Timeout in seconds for the default client.
     */
    public function __construct(string $serverurl, string $apikey = '', ?ClientInterface $http = null, int $timeout = 300) {
        $this->serverurl = rtrim($serverurl, '/');
        $this->apikey = trim($apikey);
        $this->http = $http ?? \core\di::get(http_factory::class)->create($timeout);
    }

    /**
     * Create a client from a component's admin settings (serverurl, apikey).
     *
     * @param string $component Frankenstyle component, e.g. mod_airagmaterial.
     * @param int $timeout Timeout in seconds.
     * @return self
     */
    public static function for_component(string $component, int $timeout = 300): self {
        $serverurl = (string)get_config($component, 'serverurl');
        if ($serverurl === '') {
            $serverurl = 'http://127.0.0.1:8000';
        }
        return new self($serverurl, (string)get_config($component, 'apikey'), null, $timeout);
    }

    /**
     * Upload a file for vectorization (POST /course/materials/upload).
     *
     * @param int $courseid Course id.
     * @param string $filepath Local path of the file.
     * @param string $filename Original filename.
     * @param string|null $materialid Owner id such as airagmaterial:3; omitted when null.
     * @return array Result.
     */
    public function upload_material(int $courseid, string $filepath, string $filename, ?string $materialid = null): array {
        $handle = @fopen($filepath, 'rb');
        if ($handle === false) {
            return $this->failure(0, 'Cannot read file: ' . $filename);
        }
        $parts = [
            ['name' => 'file', 'contents' => $handle, 'filename' => $filename],
            ['name' => 'course_id', 'contents' => (string)$courseid],
            ['name' => 'course_name', 'contents' => ''],
        ];
        if ($materialid !== null) {
            $parts[] = ['name' => 'material_id', 'contents' => $materialid];
        }
        return $this->request('POST', '/course/materials/upload', ['multipart' => $parts]);
    }

    /**
     * Delete the vectors of one file (DELETE /course/materials/file, form body).
     *
     * @param int $courseid Course id.
     * @param string $filename Filename.
     * @param string|null $materialid Owner id; omitted when null.
     * @return array Result.
     */
    public function delete_file(int $courseid, string $filename, ?string $materialid = null): array {
        $form = ['course_id' => (string)$courseid, 'filename' => $filename];
        if ($materialid !== null) {
            $form['material_id'] = $materialid;
        }
        return $this->request('DELETE', '/course/materials/file', ['form_params' => $form]);
    }

    /**
     * Grade an answer (POST /assign/answer).
     *
     * @param array $payload JSON payload.
     * @param string $requestid Value for the X-Request-ID header.
     * @return array Result.
     */
    public function grade(array $payload, string $requestid): array {
        return $this->request('POST', '/assign/answer', [
            'json' => $payload,
            'headers' => ['X-Request-ID' => $requestid],
        ]);
    }

    /**
     * Perform a request and normalise the outcome.
     *
     * @param string $method HTTP method.
     * @param string $path Path starting with a slash.
     * @param array $options Guzzle options.
     * @return array Result.
     */
    private function request(string $method, string $path, array $options): array {
        $options['http_errors'] = false;
        $options['headers']['Accept'] = 'application/json';
        if ($this->apikey !== '') {
            $options['headers']['Authorization'] = 'Bearer ' . $this->apikey;
        }
        try {
            $response = $this->http->request($method, $this->serverurl . $path, $options);
        } catch (GuzzleException | \RuntimeException $e) {
            return $this->failure(0, 'Connection error: ' . $e->getMessage());
        }
        return $this->parse($response);
    }

    /**
     * Convert a response to the result array.
     *
     * @param ResponseInterface $response Response.
     * @return array Result.
     */
    private function parse(ResponseInterface $response): array {
        $status = $response->getStatusCode();
        $body = (string)$response->getBody();
        $data = json_decode($body, true);
        $data = is_array($data) ? $data : [];

        if ($status !== 200) {
            $detail = $data['detail'] ?? $data['message'] ?? $body;
            if (!is_string($detail)) {
                $detail = json_encode($detail);
            }
            return $this->failure($status, "HTTP $status: " . substr($detail, 0, 500), $data);
        }
        if (!$data) {
            return $this->failure($status, 'Invalid JSON response');
        }
        if (array_key_exists('success', $data) && empty($data['success'])) {
            $message = $data['message'] ?? $data['detail'] ?? 'Server error';
            return $this->failure($status, is_string($message) ? $message : json_encode($message), $data);
        }
        return ['success' => true, 'error' => null, 'status' => $status, 'data' => $data];
    }

    /**
     * Build a failure result.
     *
     * @param int $status HTTP status (0 when none).
     * @param string $error Message.
     * @param array $data Decoded body, if any.
     * @return array Result.
     */
    private function failure(int $status, string $error, array $data = []): array {
        return ['success' => false, 'error' => $error, 'status' => $status, 'data' => $data];
    }
}
