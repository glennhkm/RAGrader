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

/**
 * Language strings for AI RAG Material module.
 *
 * @package    mod_airagmaterial
 * @copyright  2025 Glenn HKM
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

$string['modulename'] = 'AI RAG Material';
$string['modulenameplural'] = 'AI RAG Materials';
$string['modulename_help'] = 'The AI RAG Material module allows teachers to upload course materials (PDF, PPTX, DOCX, TXT) that are automatically vectorized into a ChromaDB vector database. These materials serve as the knowledge base for AI RAG-powered assignment grading.';
$string['pluginname'] = 'AI RAG Material';
$string['pluginadministration'] = 'AI RAG Material administration';
$string['airagmaterialname'] = 'Material name';
$string['airagmaterialname_help'] = 'Enter a descriptive name for this material collection.';
$string['airagmaterialname_placeholder'] = 'e.g. Week 1 – Introduction to AI';
$string['airagmaterial:addinstance'] = 'Add a new AI RAG Material';
$string['airagmaterial:view'] = 'View AI RAG Material';
$string['airagmaterial:upload'] = 'Upload materials for vectorization';
$string['airagmaterial:manage'] = 'Manage AI RAG Materials';
$string['materialfiles'] = 'Material files';
$string['materialfiles_help'] = 'Upload PDF, PPTX, DOCX, or TXT files that will be automatically processed and stored in the vector database for AI RAG grading. Maximum file size: 50MB per file.';
$string['material_intro_hint'] = 'Upload your course materials here. Files will be automatically vectorized into the AI knowledge base after saving.';
$string['file_section_hint'] = 'Accepted file types: PDF, PPTX, DOCX, TXT.';
$string['vectorizestatus'] = 'Vectorization status';
$string['status_pending'] = 'Pending vectorization';
$string['status_queued'] = 'Queued for vectorization';
$string['status_processing'] = 'Processing...';;
$string['status_completed'] = 'Vectorized successfully';
$string['status_failed'] = 'Vectorization failed';
$string['totalchunks'] = 'Total chunks created';
$string['totaldocuments'] = 'Total documents loaded';
$string['vectorizeaction'] = 'Vectorize materials';
$string['revectorize'] = 'Re-vectorize materials';
$string['clearvectors'] = 'Clear vectors';
$string['confirmclear'] = 'Are you sure you want to clear all vectors for this material? This cannot be undone.';
$string['vectorizesuccess'] = 'Materials successfully vectorized! {$a->chunks} chunks created from {$a->documents} documents.';
$string['vectorizeerror'] = 'Error vectorizing materials: {$a}';
$string['autovectorizesuccess'] = 'Files automatically vectorized on upload! {$a->chunks} chunks created from {$a->documents} documents.';
$string['autovectorizeerror'] = 'Auto-vectorization failed after upload: {$a}. You can retry using the Re-vectorize button.';
$string['autovectorize_info'] = 'Files are automatically vectorized when uploaded. Use the Re-vectorize button if you need to reprocess the materials.';
$string['nofiles'] = 'No files have been uploaded yet.';
$string['uploadedfiles'] = 'Uploaded files';
$string['filecount'] = '{$a} file(s) uploaded';
$string['maxfilesize'] = 'Maximum file size: 50MB per file';
$string['allowedfiletypes'] = 'Allowed file types: PDF, PPTX, DOCX, TXT';
$string['serverurl'] = 'RAG Server URL';
$string['serverurl_desc'] = 'The URL of the RAG API server (e.g., http://127.0.0.1:8000)';
$string['apikey'] = 'API Key (Optional)';
$string['apikey_desc'] = 'Optional bearer token matching API_AUTH_TOKEN on the RAG API server.';
$string['servererror'] = 'Could not connect to the RAG server. Please check the server URL in plugin settings.';
$string['privacy:metadata'] = 'The AI RAG Material plugin stores course material only and holds no personal data about users. Files you add are sent to the configured RAG server for vectorization.';
$string['description'] = 'Description';
$string['materialsheader'] = 'Material files';
$string['vectorstatus'] = 'Vector Database Status';
$string['documentsindb'] = 'Documents in vector database';
$string['chunksindb'] = 'Chunks in vector database';
$string['lastprocessed'] = 'Last processed';
$string['never'] = 'Never';
$string['indicator:cognitivedepth'] = 'AI RAG Material cognitive';
$string['indicator:cognitivedepth_help'] = 'This indicator is based on the cognitive depth reached by the student in an AI RAG Material resource.';
$string['indicator:socialbreadth'] = 'AI RAG Material social';
$string['indicator:socialbreadth_help'] = 'This indicator is based on the social breadth reached by the student in an AI RAG Material resource.';
$string['search:activity'] = 'AI RAG Material';
$string['task_vectorize'] = 'Vectorize AI RAG Material';
$string['vectorize_queued_notice'] = 'Vectorization has been queued. It will run in the background — you can navigate away and come back later.';
$string['vectorize_processing_title'] = 'Vectorization in progress';
$string['queue_navigate_away'] = 'You can navigate away and come back later.';
$string['clearvectors_busy'] = 'Vectors cannot be cleared while vectorization is queued or in progress. Please wait for it to finish.';
$string['clearvectors_success'] = 'Vectors for this material were cleared. Other materials in the course were not affected.';
$string['clearvectors_failed'] = 'The RAG server could not remove vectors for: {$a}. Please try clearing again.';
$string['clearvectors_retained'] = 'Vectors for {$a} were kept because another activity in this course uses a file with the same name.';
$string['stalevectors_cleanup_failed'] = 'Could not remove vectors of files that were deleted from this material: {$a}.';
$string['upgrade_revectorize_notice'] = '{$a} material(s) will be re-vectorized in the background after this upgrade so their vectors are owned by each material. AI grading waits until vectorization finishes (materials show as queued until then).';
