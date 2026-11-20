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
 * Library of interface functions and constants for AI RAG Material module.
 *
 * @package    mod_airagmaterial
 * @copyright  2025 Glenn HKM
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

/** Maximum file size: 50MB */
define('AIRAGMATERIAL_MAX_FILESIZE', 50 * 1024 * 1024);

/** Allowed file types for upload */
define('AIRAGMATERIAL_ALLOWED_TYPES', '.pdf,.pptx,.docx,.txt');

/**
 * Returns the features supported by this module.
 *
 * @param string $feature FEATURE_xx constant for requested feature
 * @return mixed True if feature is supported, null if unknown
 */
function airagmaterial_supports($feature) {
    switch ($feature) {
        case FEATURE_MOD_INTRO:
            return true;
        case FEATURE_SHOW_DESCRIPTION:
            return true;
        case FEATURE_BACKUP_MOODLE2:
            return true;
        case FEATURE_MOD_PURPOSE:
            return MOD_PURPOSE_CONTENT;
        default:
            return null;
    }
}

/**
 * Add a new AI RAG Material instance.
 *
 * @param stdClass $data Form data
 * @param mod_airagmaterial_mod_form $mform The form
 * @return int The new instance id
 */
function airagmaterial_add_instance($data, $mform = null) {
    global $DB, $SESSION;

    $data->timecreated = time();
    $data->timemodified = time();
    $data->vectorize_status = 'pending';
    $data->chunks_created = 0;
    $data->documents_loaded = 0;
    $data->total_in_db = 0;
    $data->last_vectorized = 0;
    $data->revision = 0;

    $data->id = $DB->insert_record('airagmaterial', $data);

    // Save uploaded files.
    $cmid = $data->coursemodule;
    $DB->set_field('course_modules', 'instance', $data->id, ['id' => $cmid]);
    $context = context_module::instance($cmid);

    if (isset($data->materialfiles)) {
        file_save_draft_area_files(
            $data->materialfiles,
            $context->id,
            'mod_airagmaterial',
            'materials',
            0,
            airagmaterial_get_filemanager_options()
        );
    }

    // Auto-vectorize in background — queue an adhoc task so the form save
    // returns immediately and the teacher does not have to wait.
    $material_record = $DB->get_record('airagmaterial', ['id' => $data->id]);
    airagmaterial_queue_vectorize_task($material_record, (int)$context->id);

    return $data->id;
}

/**
 * Update an existing AI RAG Material instance.
 *
 * @param stdClass $data Form data
 * @param mod_airagmaterial_mod_form $mform The form
 * @return bool True on success
 */
function airagmaterial_update_instance($data, $mform = null) {
    global $DB, $SESSION;

    $data->timemodified = time();
    $data->id = $data->instance;

    // Load current record to get revision counter.
    $current = $DB->get_record('airagmaterial', ['id' => $data->id], '*', MUST_EXIST);
    $data->revision = $current->revision + 1;

    // Preserve existing vectorize fields that are not in the form.
    $data->vectorize_status = $current->vectorize_status;
    $data->chunks_created = $current->chunks_created;
    $data->documents_loaded = $current->documents_loaded;
    $data->total_in_db = $current->total_in_db;
    $data->last_vectorized = $current->last_vectorized;
    $data->vectorize_error = $current->vectorize_error;

    $DB->update_record('airagmaterial', $data);

    // Save uploaded files.
    $cmid = $data->coursemodule;
    $context = context_module::instance($cmid);

    if (isset($data->materialfiles)) {
        file_save_draft_area_files(
            $data->materialfiles,
            $context->id,
            'mod_airagmaterial',
            'materials',
            0,
            airagmaterial_get_filemanager_options()
        );

        // Auto-vectorize in background — queue an adhoc task so the edit form
        // save returns instantly and the teacher does not have to wait.
        $material_fresh = $DB->get_record('airagmaterial', ['id' => $data->id], '*', MUST_EXIST);
        airagmaterial_queue_vectorize_task($material_fresh, (int)$context->id);
    }

    return true;
}

/**
 * Queue a background vectorization adhoc task for the given material.
 *
 * Sets vectorize_status = 'queued' immediately (so the UI can show a spinner
 * right away) and then schedules the actual API call via Moodle's cron queue.
 * The task class is mod_airagmaterial\task\vectorize_material.
 *
 * @param stdClass $material  The airagmaterial DB record.
 * @param int      $contextid The context_module ID for the material.
 * @return void
 */
function airagmaterial_queue_vectorize_task($material, $contextid) {
    global $DB;

    // Mark as queued immediately so the view page can show a spinner at once.
    $DB->set_field('airagmaterial', 'vectorize_status', 'queued', ['id' => $material->id]);
    // Clear any previous error so it does not appear during the new attempt.
    $DB->set_field('airagmaterial', 'vectorize_error', null, ['id' => $material->id]);

    $task = new \mod_airagmaterial\task\vectorize_material();
    $task->set_custom_data([
        'materialid' => (int)$material->id,
        'contextid'  => (int)$contextid,
    ]);
    $task->set_component('mod_airagmaterial');

    // Pass true to avoid queuing a duplicate if a task is already waiting.
    \core\task\manager::queue_adhoc_task($task, true);
}

/**
 * Delete an AI RAG Material instance.
 *
 * Also removes all associated vector chunks from the RAG server so that
 * no orphaned embeddings are left behind in ChromaDB (storage hygiene).
 *
 * @param int $id Instance ID
 * @return bool True on success
 */
function airagmaterial_delete_instance($id) {
    global $DB;

    $material = $DB->get_record('airagmaterial', ['id' => $id]);
    if (!$material) {
        // Record already gone — deletion is effectively complete.
        return true;
    }

    // NOTE: Vector cleanup is handled by airagmaterial_pre_course_module_delete()
    // which is called by Moodle core BEFORE this function, while the DB rows still
    // exist. We must NOT re-call it here to avoid double-delete attempts.

    // Delete DB records.
    $DB->delete_records('airagmaterial_files', ['materialid' => $id]);
    $DB->delete_records('airagmaterial', ['id' => $id]);

    return true;
}

/**
 * Hook: called by Moodle core (course/lib.php::course_delete_module) immediately
 * BEFORE the module instance is deleted.  At this point the airagmaterial and
 * airagmaterial_files rows still exist, so we can look up filenames and call the
 * RAG API to remove the vector embeddings from ChromaDB.
 *
 * Moodle discovers this function via get_plugins_with_function('pre_course_module_delete').
 *
 * @param stdClass $cm  The course_modules record (includes ->modname, ->instance, ->course).
 */
function airagmaterial_pre_course_module_delete($cm) {
    global $DB;

    // Only act on airagmaterial modules.
    if ($cm->modname !== 'airagmaterial') {
        return;
    }

    $material = $DB->get_record('airagmaterial', ['id' => $cm->instance]);
    if (!$material) {
        return;
    }

    // Clean up every tracked file regardless of the material status: a failed
    // or re-queued run can still leave vectors from an earlier successful run.
    airagmaterial_delete_material_vectors($material, airagmaterial_get_tracked_filenames((int)$material->id));
}

/**
 * Return the distinct filenames tracked for a material (vectorized or not).
 *
 * @param int $materialid AI RAG Material instance ID.
 * @return string[] Filenames.
 */
function airagmaterial_get_tracked_filenames(int $materialid): array {
    global $DB;

    $names = $DB->get_fieldset_select('airagmaterial_files', 'filename', 'materialid = :materialid',
        ['materialid' => $materialid]);
    return array_values(array_unique(array_filter(array_map('strval', $names), 'strlen')));
}

/**
 * Delete the RAG vectors of the given files belonging to one material.
 *
 * Only vectors for this material's files are touched; the rest of the course
 * collection (other materials, assignment reference files) is left intact.
 * Files whose name is still used by another activity in the same course are
 * retained, because the backend identifies chunks by filename only.
 *
 * @param stdClass $material The airagmaterial record.
 * @param string[] $filenames Filenames to remove from the vector store.
 * @return array{deleted: string[], retained: string[], failed: string[]}
 */
function airagmaterial_delete_material_vectors(stdClass $material, array $filenames): array {
    $result = ['deleted' => [], 'retained' => [], 'failed' => []];

    foreach (array_unique($filenames) as $filename) {
        $filename = (string)$filename;
        if ($filename === '') {
            continue;
        }
        if (\mod_airagmaterial\local\vector_ownership::is_filename_in_use(
                (int)$material->course, $filename, (int)$material->id)) {
            $result['retained'][] = $filename;
            continue;
        }
        if (airagmaterial_delete_file_vectors($material->course, $filename)) {
            $result['deleted'][] = $filename;
        } else {
            $result['failed'][] = $filename;
        }
    }

    return $result;
}

/**
 * Build HTTP headers for RAG API requests, appending Bearer auth when configured.
 *
 * @param array $headers Base HTTP headers
 * @return array Complete HTTP headers
 */
function airagmaterial_build_api_headers(array $headers = []): array {
    $apikey = trim((string)get_config('mod_airagmaterial', 'apikey'));
    if ($apikey !== '') {
        $headers[] = 'Authorization: Bearer ' . $apikey;
    }
    return $headers;
}

/**
 * Delete all vector chunks for a single file from the RAG server.
 *
 * Calls DELETE /course/materials/file with course_id + filename.
 * Failures are logged but intentionally do not throw — a failed vector
 * cleanup must not block the Moodle course-module deletion.
 *
 * @param int    $courseid  Moodle course ID.
 * @param string $filename  Basename of the file to remove.
 * @return bool True if the API call succeeded.
 */
function airagmaterial_delete_file_vectors($courseid, $filename) {
    $result = \mod_airagmaterial\local\rag_client::for_component('mod_airagmaterial', 30)
        ->delete_file((int)$courseid, (string)$filename);

    if (!$result['success']) {
        // Log the error but let the Moodle deletion proceed regardless.
        debugging(
            "airagmaterial_delete_file_vectors: failed to delete vectors for '$filename' " .
            "(course $courseid). HTTP {$result['status']} — {$result['error']}",
            DEBUG_DEVELOPER
        );
        return false;
    }

    return true;
}

/**
 * Get filemanager options for material uploads.
 *
 * @return array Filemanager options
 */
function airagmaterial_get_filemanager_options() {
    return [
        'subdirs' => false,
        'maxbytes' => AIRAGMATERIAL_MAX_FILESIZE,
        'maxfiles' => 20,
        'accepted_types' => explode(',', AIRAGMATERIAL_ALLOWED_TYPES),
    ];
}

/**
 * Serves the files from the airagmaterial file areas.
 *
 * @param stdClass $course Course object
 * @param stdClass $cm Course module object
 * @param stdClass $context Context object
 * @param string $filearea File area
 * @param array $args Extra arguments
 * @param bool $forcedownload Force download
 * @param array $options Additional options
 * @return bool False if file not found
 */
function airagmaterial_pluginfile($course, $cm, $context, $filearea, $args, $forcedownload, array $options = []) {
    if ($context->contextlevel != CONTEXT_MODULE) {
        return false;
    }

    require_course_login($course, true, $cm);

    if ($filearea !== 'materials') {
        return false;
    }

    $itemid = array_shift($args);
    $filename = array_pop($args);
    $filepath = $args ? '/' . implode('/', $args) . '/' : '/';

    $fs = get_file_storage();
    $file = $fs->get_file($context->id, 'mod_airagmaterial', $filearea, $itemid, $filepath, $filename);

    if (!$file) {
        return false;
    }

    send_stored_file($file, 0, 0, $forcedownload, $options);
}

/**
 * Get the list of uploaded files for a material instance.
 *
 * @param int $contextid The context ID
 * @return array List of stored_file objects
 */
function airagmaterial_get_uploaded_files($contextid) {
    $fs = get_file_storage();
    $files = $fs->get_area_files($contextid, 'mod_airagmaterial', 'materials', 0, 'filename', false);
    return $files;
}

/**
 * Called by Moodle to get view actions for participation report.
 *
 * @return array
 */
function airagmaterial_get_view_actions() {
    return ['view', 'view all'];
}

/**
 * Called by Moodle to get post actions for participation report.
 *
 * @return array
 */
function airagmaterial_get_post_actions() {
    return ['upload', 'vectorize'];
}

/**
 * Vectorize uploaded materials by sending them to the RAG server.
 *
 * @param stdClass $material The material record
 * @param context_module $context The module context
 * @return array Result with success status
 */
function airagmaterial_vectorize_files($material, $context) {
    global $DB;

    $serverurl = get_config('mod_airagmaterial', 'serverurl');
    if (empty($serverurl)) {
        $serverurl = 'http://127.0.0.1:8000';
    }

    // Get uploaded files.
    $files = airagmaterial_get_uploaded_files($context->id);
    $currentnames = [];
    foreach ($files as $file) {
        $currentnames[] = $file->get_filename();
    }

    // Files removed from the material since the last run would otherwise keep
    // their chunks in the course collection forever (orphaned vectors).
    $stalenames = array_values(array_diff(airagmaterial_get_tracked_filenames((int)$material->id), $currentnames));
    $cleanup = airagmaterial_delete_material_vectors($material, $stalenames);
    $cleanupwarnings = [];
    if (!empty($cleanup['failed'])) {
        $cleanupwarnings[] = get_string('stalevectors_cleanup_failed', 'airagmaterial',
            implode(', ', $cleanup['failed']));
    }

    if (empty($files)) {
        // Nothing left to vectorize: reset to a terminal state instead of
        // leaving the material stuck in 'queued' with a spinner forever.
        $DB->delete_records('airagmaterial_files', ['materialid' => $material->id]);
        $material->vectorize_status = 'pending';
        $material->chunks_created = 0;
        $material->documents_loaded = 0;
        $material->total_in_db = 0;
        $material->vectorize_error = $cleanupwarnings ? implode("\n", $cleanupwarnings) : null;
        $DB->update_record('airagmaterial', $material);
        return ['success' => false, 'error' => get_string('nofiles', 'airagmaterial'),
            'chunks' => 0, 'documents' => 0, 'errors' => [get_string('nofiles', 'airagmaterial')]];
    }

    // Update status to processing.
    $material->vectorize_status = 'processing';
    $DB->update_record('airagmaterial', $material);

    // Delete old file tracking records (their vectors are replaced or cleaned up above).
    $DB->delete_records('airagmaterial_files', ['materialid' => $material->id]);

    $totalchunks = 0;
    $totaldocs = 0;
    $errors = [];

    foreach ($files as $file) {
        $filename = $file->get_filename();
        $filesize = $file->get_filesize();
        $mimetype = $file->get_mimetype();
        $contenthash = $file->get_contenthash();

        // Track file.
        $filerecord = new stdClass();
        $filerecord->materialid = $material->id;
        $filerecord->filename = $filename;
        $filerecord->filesize = $filesize;
        $filerecord->mimetype = $mimetype;
        $filerecord->contenthash = $contenthash;
        $filerecord->vectorized = 0;
        $filerecord->chunks_count = 0;
        $filerecord->timecreated = time();
        $filerecord->id = $DB->insert_record('airagmaterial_files', $filerecord);

        // Create a temp file for curl upload.
        $tempdir = make_temp_directory('airagmaterial');
        $tempfile = $tempdir . '/' . $filename;
        $file->copy_content_to($tempfile);

        // Send to RAG server.
        $result = airagmaterial_send_file_to_rag($serverurl, $tempfile, $filename, $material->course);

        // Clean up temp file.
        @unlink($tempfile);

        if ($result['success']) {
            $filerecord->vectorized = 1;
            $filerecord->chunks_count = $result['chunks_created'] ?? 0;
            $DB->update_record('airagmaterial_files', $filerecord);
            $totalchunks += $filerecord->chunks_count;
            $totaldocs += ($result['documents_loaded'] ?? 1);
        } else {
            $filerecord->error_message = $result['error'] ?? 'Unknown error';
            $DB->update_record('airagmaterial_files', $filerecord);
            $errors[] = $filename . ': ' . ($result['error'] ?? 'Unknown error');
        }
    }

    // Update material record. Partial success is still 'completed' (only the
    // successfully vectorized files are used for scoped retrieval), but the
    // per-file errors and cleanup warnings stay visible to the teacher.
    $material->vectorize_status = (empty($errors) || $totaldocs > 0) ? 'completed' : 'failed';
    $messages = array_merge($errors, $cleanupwarnings);
    $material->vectorize_error = $messages ? implode("\n", $messages) : null;
    $material->chunks_created = $totalchunks;
    $material->documents_loaded = $totaldocs;
    $material->last_vectorized = time();
    $DB->update_record('airagmaterial', $material);

    return [
        'success' => empty($errors) || $totaldocs > 0,
        'chunks' => $totalchunks,
        'documents' => $totaldocs,
        'errors' => $errors,
    ];
}

/**
 * Send a single file to the RAG server for vectorization.
 *
 * @param string $serverurl RAG server base URL
 * @param string $filepath Local file path
 * @param string $filename Original filename
 * @param int $courseid Course ID
 * @return array Result array
 */
function airagmaterial_send_file_to_rag($serverurl, $filepath, $filename, $courseid) {
    $client = new \mod_airagmaterial\local\rag_client(
        (string)$serverurl,
        (string)get_config('mod_airagmaterial', 'apikey')
    );
    $result = $client->upload_material((int)$courseid, $filepath, $filename);

    if (!$result['success']) {
        return ['success' => false, 'error' => $result['error']];
    }

    $data = $result['data'];
    if (empty($data['success'])) {
        return ['success' => false, 'error' => $data['message'] ?? $data['detail'] ?? 'Server error'];
    }

    return [
        'success' => true,
        'chunks_created' => $data['chunk_count'] ?? $data['chunks_created'] ?? 0,
        'documents_loaded' => $data['documents_loaded'] ?? 1,
        'total_in_db' => $data['total_documents_in_db'] ?? 0,
    ];
}
