<?php
// This file is part of Moodle - https://moodle.org/
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
// along with Moodle.  If not, see <https://www.gnu.org/licenses/>.

namespace local_assign_ai_rag\api;

use local_assign_ai_rag\utils;

/**
 * Client API for local_assign_ai_rag.
 * 
 * This client handles communication with the RAG server for essay grading.
 * It sends the submission payload to the RAG pipeline which uses course
 * materials as context for grading.
 *
 * @package     local_assign_ai_rag
 * @copyright   2025 Glenn H. K. M.
 * @license     https://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */
class client {
    
    /** @var string|null Cached server URL */
    private static ?string $serverurl = null;
    
    /** @var string|null Cached API key */
    private static ?string $apikey = null;
    
    /** @var int Cached timeout */
    private static int $timeout = 120;

    /**
     * Get the configured server URL from plugin settings.
     *
     * @return string The server URL.
     */
    protected static function get_server_url(): string {
        if (self::$serverurl === null) {
            // Current setting names, with fallbacks for early development builds.
            self::$serverurl = get_config('local_assign_ai_rag', 'server_url')
                ?: get_config('local_assign_ai_rag', 'ragserverurl')
                ?: 'http://127.0.0.1:8000';
            self::$apikey = get_config('local_assign_ai_rag', 'api_key')
                ?: get_config('local_assign_ai_rag', 'ragapikey')
                ?: '';
            self::$timeout = (int) (get_config('local_assign_ai_rag', 'timeout')
                ?: get_config('local_assign_ai_rag', 'ragtimeout')
                ?: 120);
        }
        
        return rtrim(self::$serverurl, '/');
    }

    /**
     * Make an HTTP request to the RAG server.
     *
     * @param string $method HTTP method (GET, POST, etc.)
     * @param string $endpoint API endpoint (e.g., '/assign/answer')
     * @param array|null $data Data to send (for POST requests)
     * @return array The JSON-decoded response.
     * @throws \moodle_exception On error.
     */
    protected static function request(string $method, string $endpoint, ?array $data = null): array {
        $url = self::get_server_url() . $endpoint;
        
        // Use native PHP curl for reliability
        $ch = curl_init($url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_TIMEOUT, self::$timeout);
        curl_setopt($ch, CURLOPT_CONNECTTIMEOUT, 30);
        curl_setopt($ch, CURLOPT_HTTPHEADER, [
            'Content-Type: application/json',
            'Accept: application/json',
        ]);
        
        if ($method === 'POST' && $data !== null) {
            curl_setopt($ch, CURLOPT_POST, true);
            curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($data));
        } else if ($method === 'DELETE') {
            curl_setopt($ch, CURLOPT_CUSTOMREQUEST, 'DELETE');
        }
        
        // Add API key if configured
        if (!empty(self::$apikey)) {
            curl_setopt($ch, CURLOPT_HTTPHEADER, [
                'Content-Type: application/json',
                'Accept: application/json',
                'Authorization: Bearer ' . self::$apikey,
            ]);
        }
        
        $response = curl_exec($ch);
        $errno = curl_errno($ch);
        $error = curl_error($ch);
        $httpcode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);
        
        if ($errno) {
            debugging("CURL error ($errno): $error", DEBUG_DEVELOPER);
            throw new \moodle_exception('curlerror', 'local_assign_ai_rag', '', $error);
        }
        
        if ($httpcode >= 400) {
            debugging("HTTP error: $httpcode Response: " . substr($response, 0, 500), DEBUG_DEVELOPER);
            throw new \moodle_exception('httperror', 'local_assign_ai_rag', '', $httpcode);
        }

        // Handle empty response
        if (empty($response)) {
            debugging("Empty response from RAG server (HTTP: $httpcode)", DEBUG_DEVELOPER);
            throw new \moodle_exception('error:serverconnection', 'local_assign_ai_rag');
        }

        $decoded = json_decode($response, true);
        if (json_last_error() !== JSON_ERROR_NONE) {
            debugging("JSON decode error: " . json_last_error_msg() . " Response: " . substr($response, 0, 1000), DEBUG_DEVELOPER);
            throw new \moodle_exception('jsondecodeerror', 'local_assign_ai_rag', '', json_last_error_msg());
        }

        return $decoded;
    }

    /**
     * Sends the payload to the RAG AI provider and returns the response.
     *
     * @param array $payload The request payload.
     * @return array The AI response.
     * @throws \moodle_exception On communication error.
     */
    public static function send_to_ai(array $payload): array {
        // Normalize payload to match RAG server expectations
        $payload = utils::normalize_payload($payload);
        
        // Convert to RAG server format
        $ragpayload = self::convert_to_rag_format($payload);

        // Send to RAG server's Moodle-compatible endpoint
        $response = self::request('POST', '/assign/answer', $ragpayload);

        // Convert response back to expected format
        return self::convert_from_rag_response($response);
    }

    /**
     * Convert Moodle payload format to RAG server format.
     * The payload from build_payload() is already in the correct format.
     *
     * @param array $payload Original payload from build_payload().
     * @return array Converted payload for RAG server.
     */
    protected static function convert_to_rag_format(array $payload): array {
        // Ensure rubric is an object (associative array), not empty array
        $rubric = $payload['rubric'] ?? null;
        if (empty($rubric) || (is_array($rubric) && empty($rubric))) {
            // Convert to stdClass so JSON encodes as {} not []
            $rubric = new \stdClass();
        }
        
        // Payload is already in correct format from build_payload()
        return [
            'course_id' => (int)($payload['course_id'] ?? 0),
            'question' => $payload['question'] ?? '',
            'essay' => $payload['essay'] ?? '',
            'rubric' => $rubric,
            'maximum_grade' => (float)($payload['maximum_grade'] ?? 100),
        ];
    }

    /**
     * Convert RAG server response to expected Moodle format.
     *
     * @param array $response RAG server response.
     * @return array Converted response.
     */
    protected static function convert_from_rag_response(array $response): array {
        // Handle success/failure
        if (!($response['success'] ?? true)) {
            return [
                'success' => false,
                'error' => $response['error'] ?? $response['feedback'] ?? 'Error during AI grading.',
                'feedback' => $response['feedback'] ?? $response['error'] ?? 'Error during AI grading.',
                'grade' => null,
                'rubric_scores' => [],
                'citations' => [],
                'confidence' => 0.0,
                'retrieved_documents' => [],
            ];
        }

        return [
            'success' => true,
            'error' => null,
            'feedback' => $response['feedback'] ?? '',
            'grade' => $response['score'] ?? null,
            'rubric_scores' => $response['criterion_scores'] ?? [],
            'citations' => $response['citations'] ?? [],
            'confidence' => $response['confidence'] ?? 0.0,
            'retrieved_documents' => $response['retrieved_documents'] ?? [],
        ];
    }

    /**
     * Upload course materials to RAG server.
     *
     * @param int $courseid Course ID.
     * @param array $files Array of stored_file objects or file paths to upload.
     * @param array $options Reserved upload options.
     * @return array Upload result.
     * @throws \moodle_exception On error.
     */
    public static function upload_materials(int $courseid, array $files, array $options = []): array {
        $url = self::get_server_url() . '/course/materials/upload';
        $results = [];
        $chunkcount = 0;
        $documentsloaded = 0;

        foreach ($files as $file) {
            $temppath = null;
            if ($file instanceof \stored_file) {
                $temppath = make_temp_directory('local_assign_ai_rag') . '/' . $file->get_filename();
                $file->copy_content_to($temppath);
                $filepath = $temppath;
                $filename = $file->get_filename();
                $mimetype = $file->get_mimetype();
            } else if (is_string($file) && file_exists($file)) {
                $filepath = $file;
                $filename = basename($file);
                $mimetype = mime_content_type($file) ?: 'application/octet-stream';
            } else {
                throw new \moodle_exception('error:invaliduploadfile', 'local_assign_ai_rag');
            }

            try {
                $headers = ['Accept: application/json'];
                if (!empty(self::$apikey)) {
                    $headers[] = 'Authorization: Bearer ' . self::$apikey;
                }

                $ch = curl_init($url);
                curl_setopt_array($ch, [
                    CURLOPT_POST => true,
                    CURLOPT_POSTFIELDS => [
                        'file' => new \CURLFile($filepath, $mimetype, $filename),
                        'course_id' => (string) $courseid,
                    ],
                    CURLOPT_HTTPHEADER => $headers,
                    CURLOPT_RETURNTRANSFER => true,
                    CURLOPT_CONNECTTIMEOUT => 30,
                    CURLOPT_TIMEOUT => self::$timeout * 2,
                ]);
                $response = curl_exec($ch);
                $curlerror = curl_error($ch);
                $httpcode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
                curl_close($ch);

                $decoded = json_decode((string) $response, true);
                if ($curlerror || $httpcode >= 400 || !is_array($decoded) || empty($decoded['success'])) {
                    debugging(
                        "Material upload failed for {$filename} (HTTP {$httpcode}): "
                            . ($curlerror ?: substr((string) $response, 0, 500)),
                        DEBUG_DEVELOPER
                    );
                    throw new \moodle_exception('error:materialuploadfailed', 'local_assign_ai_rag', '', $filename);
                }

                $results[] = $decoded;
                $chunkcount += (int) ($decoded['chunk_count'] ?? 0);
                $documentsloaded += (int) ($decoded['documents_loaded'] ?? 0);
            } finally {
                if ($temppath !== null && file_exists($temppath)) {
                    unlink($temppath);
                }
            }
        }

        return [
            'success' => true,
            'course_id' => $courseid,
            'files_processed' => count($results),
            'chunk_count' => $chunkcount,
            'documents_loaded' => $documentsloaded,
            'results' => $results,
        ];
    }

    /**
     * Get RAG server status.
     *
     * @return array Status information.
     */
    public static function get_server_status(): array {
        try {
            return self::request('GET', '/moodle/status');
        } catch (\Exception $e) {
            return [
                'healthy' => false,
                'error' => $e->getMessage(),
            ];
        }
    }

    /**
     * Check if RAG server is available.
     *
     * @return bool True if server is healthy.
     */
    public static function is_server_available(): bool {
        $status = self::get_server_status();
        return ($status['ready'] ?? false) === true
            || ($status['status'] ?? '') === 'healthy';
    }

    /**
     * Get collection stats for a course.
     *
     * @param int $courseid Course ID.
     * @return array Collection information.
     */
    public static function get_collection_stats(int $courseid): array {
        try {
            return self::request('GET', '/collections/' . $courseid);
        } catch (\Exception $e) {
            return [
                'document_count' => 0,
                'error' => $e->getMessage(),
            ];
        }
    }

    /**
     * Clear collection for a course.
     *
     * @param int $courseid Course ID.
     * @return bool True on success.
     */
    public static function clear_collection(int $courseid): bool {
        $url = self::get_server_url() . '/course/materials/clear';
        $headers = [
            'Accept: application/json',
            'Content-Type: application/x-www-form-urlencoded',
        ];
        if (!empty(self::$apikey)) {
            $headers[] = 'Authorization: Bearer ' . self::$apikey;
        }

        $ch = curl_init($url);
        curl_setopt_array($ch, [
            CURLOPT_POST => true,
            CURLOPT_POSTFIELDS => http_build_query(['course_id' => (string) $courseid]),
            CURLOPT_HTTPHEADER => $headers,
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_CONNECTTIMEOUT => 30,
            CURLOPT_TIMEOUT => self::$timeout,
        ]);
        $response = curl_exec($ch);
        $httpcode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $curlerror = curl_error($ch);
        curl_close($ch);

        if ($curlerror || $httpcode !== 200 || empty($response)) {
            return false;
        }

        $result = json_decode($response, true);
        return is_array($result) && !empty($result['success']);
    }
}
