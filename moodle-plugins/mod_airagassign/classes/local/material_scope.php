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

use mod_airagmaterial\local\rag_client;

/**
 * The knowledge-base scope of an assignment: linked AI RAG Materials and the manual reference file.
 *
 * @package    mod_airagassign
 * @copyright  2026 RAGrader
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */
class material_scope {
    /**
     * Manual reference files of an assignment.
     *
     * @param int $contextid Module context ID
     * @return \stored_file[] Files keyed by pathname hash, sorted by filename
     */
    public static function manual_files(int $contextid): array {
        return get_file_storage()->get_area_files($contextid, 'mod_airagassign', 'manualfile', 0, 'filename', false);
    }

    /**
     * Return the linked AI RAG Material activities that are not ready for grading.
     *
     * Grading scopes retrieval to the linked materials, so grading while one of
     * them is still queued, processing, pending or failed would silently use a
     * smaller knowledge base than the teacher selected, and students graded in the
     * same batch could be judged against different evidence. Callers must refuse
     * to grade while this list is non-empty. Per-file failures inside a
     * 'completed' material are intentionally tolerated: they are shown to the
     * teacher on the material page and only the vectorized files are used.
     *
     * @param int $assignid Assignment instance ID
     * @return array List of objects with id, name and vectorize_status
     */
    public static function unready_materials(int $assignid): array {
        global $DB;

        $sql = "SELECT am.id, am.name, am.vectorize_status
                  FROM {airagassign_materials} aam
                  JOIN {airagmaterial} am ON am.id = aam.materialid
                 WHERE aam.assignid = :assignid
                   AND (am.vectorize_status IS NULL OR am.vectorize_status <> :completed)
              ORDER BY am.name ASC, am.id ASC";
        return array_values($DB->get_records_sql($sql, ['assignid' => $assignid, 'completed' => 'completed']));
    }

    /**
     * Describe unready linked materials as "Name (status)" for teacher-facing errors.
     *
     * The result is plain text: callers store it as the grading error, which is
     * escaped with s() when displayed.
     *
     * @param array $materials Result of unready_materials()
     * @param \context $context Context used to format material names
     * @return string Comma-separated description
     */
    public static function describe_unready(array $materials, \context $context): string {
        $sm = get_string_manager();
        $parts = [];
        foreach ($materials as $material) {
            $status = (string)($material->vectorize_status ?? '');
            $status = $status === '' ? 'pending' : $status;
            $label = $sm->string_exists('status_' . $status, 'airagmaterial')
                ? get_string('status_' . $status, 'airagmaterial')
                : $status;
            $name = format_string($material->name, true, ['context' => $context, 'escape' => false]);
            $parts[] = $name . ' (' . $label . ')';
        }
        return implode(', ', $parts);
    }

    /**
     * Collect linked airagmaterial filenames and manual reference filenames for scoped RAG retrieval.
     *
     * Only vectorized files of completed materials and manual reference files
     * whose current content has been vectorized are included.
     *
     * @param int $assignid Assignment instance ID
     * @param int $contextid Module context ID
     * @return array List of unique material basenames
     */
    public static function linked_filenames(int $assignid, int $contextid): array {
        global $DB;

        $filenames = [];
        // {airagmaterial_files} tracks per-file vectorization via `vectorized` (0/1),
        // while `vectorize_status` lives on {airagmaterial}.
        $sql = "SELECT DISTINCT af.filename
                  FROM {airagassign_materials} aam
                  JOIN {airagmaterial} am ON am.id = aam.materialid
                  JOIN {airagmaterial_files} af ON af.materialid = am.id
                 WHERE aam.assignid = :assignid
                   AND am.vectorize_status = 'completed'
                   AND af.vectorized = 1";
        $records = $DB->get_records_sql($sql, ['assignid' => $assignid]);
        foreach ($records as $record) {
            $name = basename(trim((string)($record->filename ?? '')));
            if ($name !== '' && $name !== '.' && $name !== '..') {
                $filenames[$name] = true;
            }
        }

        foreach (self::ready_manual_files($assignid, $contextid) as $file) {
            $name = basename(trim((string)$file->get_filename()));
            if ($name !== '' && $name !== '.' && $name !== '..') {
                $filenames[$name] = true;
            }
        }

        return array_keys($filenames);
    }

    /**
     * Owner ids that scope grading retrieval (sent as material_ids).
     *
     * Completed linked materials ("airagmaterial:{id}") followed by the
     * assignment itself ("airagassign:{id}") when it has vectorized manual files.
     *
     * @param int $assignid Assignment instance ID
     * @param int $contextid Module context ID
     * @return string[] Owner ids
     */
    public static function owner_ids(int $assignid, int $contextid): array {
        global $CFG, $DB;
        require_once($CFG->dirroot . '/mod/airagmaterial/lib.php');

        $sql = "SELECT am.id
                  FROM {airagassign_materials} aam
                  JOIN {airagmaterial} am ON am.id = aam.materialid
                 WHERE aam.assignid = :assignid
                   AND am.vectorize_status = 'completed'
              ORDER BY am.id ASC";
        $owners = [];
        foreach ($DB->get_fieldset_sql($sql, ['assignid' => $assignid]) as $materialid) {
            $owners[] = airagmaterial_material_owner((int)$materialid);
        }
        if (!empty(self::ready_manual_files($assignid, $contextid))) {
            $owners[] = self::manualfile_owner($assignid);
        }
        return $owners;
    }

    /**
     * Map manual reference filenames to their content hashes.
     *
     * @param int $contextid The module context ID
     * @return array<string, string> filename => contenthash
     */
    public static function manual_file_hashes(int $contextid): array {
        $hashes = [];
        foreach (self::manual_files($contextid) as $file) {
            $hashes[$file->get_filename()] = $file->get_contenthash();
        }
        return $hashes;
    }

    /**
     * Vector owner id of an assignment's manual reference files.
     *
     * @param int $assignid Assignment instance ID
     * @return string Owner id, e.g. "airagassign:7"
     */
    public static function manualfile_owner(int $assignid): string {
        return 'airagassign:' . $assignid;
    }

    /**
     * Status rows of an assignment's manual reference files, keyed by filename.
     *
     * @param int $assignid Assignment instance ID
     * @return array<string, \stdClass>
     */
    private static function manualfile_rows(int $assignid): array {
        global $DB;

        $rows = [];
        foreach ($DB->get_records('airagassign_manualfiles', ['assignid' => $assignid]) as $row) {
            $rows[$row->filename] = $row;
        }
        return $rows;
    }

    /**
     * Manual reference files whose current content is vectorized.
     *
     * @param int $assignid Assignment instance ID
     * @param int $contextid Module context ID
     * @return \stored_file[]
     */
    private static function ready_manual_files(int $assignid, int $contextid): array {
        $rows = self::manualfile_rows($assignid);
        return array_filter(self::manual_files($contextid), function (\stored_file $file) use ($rows): bool {
            $row = $rows[$file->get_filename()] ?? null;
            return $row && $row->status === 'completed' && $row->contenthash === $file->get_contenthash();
        });
    }

    /**
     * Manual reference files that are not ready for grading.
     *
     * A file is unready when it has no status row, its row is not 'completed',
     * or the stored file's content changed since it was vectorized (reported
     * as 'pending'). Callers must refuse to grade while this list is non-empty.
     *
     * @param int $assignid Assignment instance ID
     * @param int $contextid Module context ID
     * @return array List of objects with filename, status and error_message
     */
    public static function unready_manualfiles(int $assignid, int $contextid): array {
        $rows = self::manualfile_rows($assignid);
        $unready = [];
        foreach (self::manual_files($contextid) as $file) {
            $name = $file->get_filename();
            $row = $rows[$name] ?? null;
            if ($row && $row->status === 'completed' && $row->contenthash === $file->get_contenthash()) {
                continue;
            }
            $status = (!$row || $row->status === 'completed') ? 'pending' : (string)$row->status;
            $unready[] = (object)[
                'filename' => $name,
                'status' => $status,
                'error_message' => $status === 'failed' ? (string)($row->error_message ?? '') : '',
            ];
        }
        return $unready;
    }

    /**
     * Describe unready manual files as "name (Status: error)" for teacher-facing errors.
     *
     * The result is plain text: callers store it as the grading error, which is
     * escaped with s() when displayed.
     *
     * @param array $files Result of unready_manualfiles()
     * @return string Comma-separated description
     */
    public static function describe_unready_manualfiles(array $files): string {
        $parts = [];
        foreach ($files as $file) {
            $label = self::manualfile_status_label((string)$file->status);
            if (!empty($file->error_message)) {
                $label .= ': ' . $file->error_message;
            }
            $parts[] = $file->filename . ' (' . $label . ')';
        }
        return implode(', ', $parts);
    }

    /**
     * Localised label of a manual file status.
     *
     * @param string $status pending, queued, processing, completed or failed
     * @return string
     */
    public static function manualfile_status_label(string $status): string {
        return get_string_manager()->string_exists('manualfile_status_' . $status, 'airagassign')
            ? get_string('manualfile_status_' . $status, 'airagassign')
            : $status;
    }

    /**
     * Mark every current manual file 'queued' and queue the background vectorization task.
     *
     * Rows of files no longer in the file area are removed. Makes no HTTP call.
     *
     * @param int $assignid Assignment instance ID
     * @param int $contextid Module context ID
     * @return bool True when a task was queued (the assignment has manual files)
     */
    public static function queue_manualfile_vectorization(int $assignid, int $contextid): bool {
        global $DB;

        $files = self::manual_files($contextid);
        $rows = self::manualfile_rows($assignid);
        $names = [];
        foreach ($files as $file) {
            $name = $file->get_filename();
            $names[$name] = true;
            $record = (object)[
                'assignid' => $assignid,
                'filename' => $name,
                'contenthash' => $file->get_contenthash(),
                'status' => 'queued',
                'error_message' => null,
                'timemodified' => time(),
            ];
            if (isset($rows[$name])) {
                $record->id = $rows[$name]->id;
                $DB->update_record('airagassign_manualfiles', $record);
            } else {
                $DB->insert_record('airagassign_manualfiles', $record);
            }
        }
        foreach (array_diff_key($rows, $names) as $row) {
            $DB->delete_records('airagassign_manualfiles', ['id' => $row->id]);
        }
        if (empty($files)) {
            return false;
        }

        $task = new \mod_airagassign\task\vectorize_manualfile();
        $task->set_custom_data(['assignid' => $assignid]);
        $task->set_component('mod_airagassign');
        \core\task\manager::queue_adhoc_task($task, true);
        return true;
    }

    /**
     * Reconcile manual file vectors after the teacher saved the assignment.
     *
     * Vectors of removed files are deleted (owner-scoped) along with their
     * rows, and vectorization is queued when any current file is unready.
     *
     * @param int $assignid Assignment instance ID
     * @param int $courseid Course ID
     * @param int $contextid Module context ID
     * @param string[] $previousnames Manual filenames before the save
     */
    public static function sync_manualfiles(int $assignid, int $courseid, int $contextid,
            array $previousnames = []): void {
        global $DB;

        $current = self::manual_file_hashes($contextid);
        $known = array_merge($previousnames, array_keys(self::manualfile_rows($assignid)));
        foreach (array_unique($known) as $name) {
            $name = (string)$name;
            if ($name === '' || isset($current[$name])) {
                continue;
            }
            self::delete_manual_file_vectors($courseid, $name, $assignid);
            $DB->delete_records('airagassign_manualfiles', ['assignid' => $assignid, 'filename' => $name]);
        }

        if (!empty(self::unready_manualfiles($assignid, $contextid))) {
            self::queue_manualfile_vectorization($assignid, $contextid);
        }
    }

    /**
     * Queue vectorization for every assignment with manual files (used by the 1.2.0 upgrade).
     *
     * Makes no HTTP call.
     *
     * @return int Number of assignments queued
     */
    public static function queue_all_manualfiles(): int {
        global $DB;

        $count = 0;
        $fs = get_file_storage();
        foreach ($DB->get_records('airagassign', null, 'id ASC', 'id, course') as $assign) {
            $cm = get_coursemodule_from_instance('airagassign', $assign->id, $assign->course, false, IGNORE_MISSING);
            if (!$cm) {
                continue;
            }
            $context = \context_module::instance($cm->id, IGNORE_MISSING);
            if (!$context || $fs->is_area_empty($context->id, 'mod_airagassign', 'manualfile', 0, false)) {
                continue;
            }
            if (self::queue_manualfile_vectorization((int)$assign->id, (int)$context->id)) {
                $count++;
            }
        }
        return $count;
    }

    /**
     * Upload the current manual reference files with the assignment's owner id and record the outcome.
     *
     * Runs in the background task. Each row records the content hash of the
     * file that was actually uploaded, so a file replaced after the task was
     * queued is never marked as vectorized with stale content.
     *
     * @param \stdClass $assign Assignment record (id, course)
     * @param int $contextid Module context ID
     * @return array{completed: string[], failed: array<string, string>}
     */
    public static function vectorize_manualfiles(\stdClass $assign, int $contextid): array {
        global $DB;

        $assignid = (int)$assign->id;
        $files = self::manual_files($contextid);
        $rows = self::manualfile_rows($assignid);
        foreach (array_diff_key($rows, self::manual_file_hashes($contextid)) as $row) {
            $DB->delete_records('airagassign_manualfiles', ['id' => $row->id]);
        }

        $client = rag_client::for_component('mod_airagassign');
        $owner = self::manualfile_owner($assignid);
        $outcome = ['completed' => [], 'failed' => []];
        foreach ($files as $file) {
            $name = $file->get_filename();
            $hash = $file->get_contenthash();
            $row = $rows[$name] ?? (object)['assignid' => $assignid, 'filename' => $name];
            $row->status = 'processing';
            $row->timemodified = time();
            if (empty($row->id)) {
                $row->id = $DB->insert_record('airagassign_manualfiles', $row);
            } else {
                $DB->update_record('airagassign_manualfiles', $row);
            }

            $tempdir = make_request_directory();
            $tempfile = $tempdir . '/' . $name;
            $file->copy_content_to($tempfile);
            $result = $client->upload_material((int)$assign->course, $tempfile, $name, $owner);
            @unlink($tempfile);

            // The upload endpoint must confirm success explicitly.
            if ($result['success'] && empty($result['data']['success'])) {
                $result['success'] = false;
                $result['error'] = $result['data']['message'] ?? $result['data']['detail'] ?? 'Server error';
            }

            $row->contenthash = $hash;
            $row->timemodified = time();
            if ($result['success']) {
                $row->status = 'completed';
                $row->error_message = null;
                $outcome['completed'][] = $name;
            } else {
                $error = trim(strip_tags(is_string($result['error'] ?? null)
                    ? $result['error'] : (string)json_encode($result['error'] ?? 'Unknown error')));
                $row->status = 'failed';
                $row->error_message = \core_text::substr($error === '' ? 'Unknown error' : $error, 0, 1000);
                $outcome['failed'][$name] = $row->error_message;
            }
            $DB->update_record('airagassign_manualfiles', $row);
        }
        return $outcome;
    }

    /**
     * Delete the vectors of one manual reference file, scoped to the assignment's owner id.
     *
     * @param int $courseid Course ID
     * @param string $filename Manual reference filename
     * @param int $assignid Assignment instance ID
     * @return bool True if the server processed the delete (HTTP 200)
     */
    public static function delete_manual_file_vectors(int $courseid, string $filename, int $assignid): bool {
        // HTTP 200 means the server processed the delete, even when it found no vectors.
        $result = rag_client::for_component('mod_airagassign', 30)
            ->delete_file($courseid, $filename, self::manualfile_owner($assignid));
        if ($result['status'] !== 200) {
            debugging(
                "material_scope::delete_manual_file_vectors: failed to delete vectors for '$filename' " .
                "(course $courseid). HTTP {$result['status']} — " . ($result['error'] ?? ''),
                DEBUG_DEVELOPER
            );
            return false;
        }
        return true;
    }

    /**
     * Delete every manual reference file vector and status row of an assignment.
     *
     * @param \stdClass $assign Assignment record (id, course)
     * @param int|null $contextid Module context ID, when the course module still exists
     */
    public static function delete_all_manualfiles(\stdClass $assign, ?int $contextid): void {
        global $DB;

        $names = array_keys(self::manualfile_rows((int)$assign->id));
        if ($contextid) {
            $names = array_merge($names, array_keys(self::manual_file_hashes($contextid)));
        }
        foreach (array_unique($names) as $name) {
            self::delete_manual_file_vectors((int)$assign->course, (string)$name, (int)$assign->id);
        }
        $DB->delete_records('airagassign_manualfiles', ['assignid' => $assign->id]);
    }
}
