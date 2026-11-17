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

/**
 * Language strings for aiprovider_rag.
 *
 * @package     aiprovider_rag
 * @copyright   2025 Glenn H. K. M.
 * @license     https://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

$string['pluginname'] = 'RAG AI Provider';
$string['privacy:metadata'] = 'The RAG AI Provider plugin does not store any personal data.';

// Settings.
$string['serverurl'] = 'RAG Server URL';
$string['serverurl_desc'] = 'The URL of the RAG server (e.g., http://localhost:8000). This server handles essay grading with course material context.';
$string['serverurl_help'] = 'Enter the full URL of your RAG server including the protocol (http:// or https://). The default is http://localhost:8000 for local development.';
$string['apikey'] = 'API Key';
$string['apikey_desc'] = 'Optional API key for authenticating with the RAG server.';
$string['apikey_help'] = 'If your RAG server requires authentication, enter the API key here. Leave empty if no authentication is required.';
$string['timeout'] = 'Request Timeout';
$string['timeout_desc'] = 'Maximum time (in seconds) to wait for RAG server response. Default is 120 seconds.';
$string['timeout_help'] = 'The maximum number of seconds to wait for a response from the RAG server. Increase this value for slow connections or when processing large submissions.';
$string['debug'] = 'Debug Mode';
$string['debug_desc'] = 'Enable debug logging for RAG API communications.';

// Services.
$string['service_assign_ai'] = 'Assignment AI Grading';

// Actions.
$string['action_assign_answer'] = 'Grade Assignment Answer';
$string['action_grade'] = 'Grade Essay';
$string['action_upload'] = 'Upload Course Materials';
$string['action_status'] = 'Get Server Status';
$string['action_collections'] = 'Manage Collections';

// Error messages.
$string['curlerror'] = 'Connection error: {$a}';
$string['httperror'] = 'Server returned error code: {$a}';
$string['jsondecodeerror'] = 'Invalid response from RAG server.';
$string['serverunreachable'] = 'RAG server is unreachable. Please check the server URL and ensure the server is running.';
$string['invalidresponse'] = 'Invalid response from RAG server.';
$string['missingconfig'] = 'RAG server URL is not configured.';

// Status messages.
$string['serverhealthy'] = 'RAG server is healthy and ready.';
$string['serverunhealthy'] = 'RAG server is not responding.';
$string['connectiontest'] = 'Test Connection';
$string['connectiontest_desc'] = 'Test the connection to the RAG server.';
$string['connectiontestsuccess'] = 'Connection successful! RAG server is ready.';
$string['connectiontestfail'] = 'Connection failed: {$a}';

// Grading.
$string['gradingwithrag'] = 'Grading with RAG AI...';
$string['gradingerror'] = 'Error during AI grading: {$a}';
$string['gradingcomplete'] = 'AI grading complete.';
$string['nomaterialsfound'] = 'No course materials found. Please upload materials first.';

// Upload.
$string['uploadingmaterials'] = 'Uploading course materials...';
$string['uploadcomplete'] = 'Materials uploaded successfully: {$a} documents processed.';
$string['uploaderror'] = 'Error uploading materials: {$a}';

// Collections.
$string['collectioncreated'] = 'Collection created for course.';
$string['collectioncleared'] = 'Collection cleared successfully.';
$string['collectionstats'] = 'Collection contains {$a} document chunks.';
