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
use mod_airagmaterial\local\vector_ownership;

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

        foreach (self::manual_files($contextid) as $file) {
            $name = basename(trim((string)$file->get_filename()));
            if ($name !== '' && $name !== '.' && $name !== '..') {
                $filenames[$name] = true;
            }
        }

        return array_keys($filenames);
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
     * Vectorize the manual reference/answer key files on the RAG server.
     *
     * @param int $courseid Course ID
     * @param int $contextid Module context ID
     * @return array ['success' => bool, 'error' => string (on failure)]
     */
    public static function vectorize_manual_files(int $courseid, int $contextid): array {
        $files = self::manual_files($contextid);
        if (empty($files)) {
            return ['success' => false, 'error' => 'No files found to vectorize'];
        }

        $client = rag_client::for_component('mod_airagassign');
        $errors = [];
        foreach ($files as $file) {
            $filename = $file->get_filename();
            $tempfile = make_temp_directory('airagassign') . '/' . $filename;
            $file->copy_content_to($tempfile);

            $result = $client->upload_material($courseid, $tempfile, $filename);
            @unlink($tempfile);

            // The upload endpoint must confirm success explicitly.
            if ($result['success'] && empty($result['data']['success'])) {
                $result['success'] = false;
                $result['error'] = $result['data']['message'] ?? $result['data']['detail'] ?? 'Server error';
            }
            if (!$result['success']) {
                $errors[] = $filename . ': ' . ($result['error'] ?? 'Unknown error');
            }
        }

        if (!empty($errors)) {
            return ['success' => false, 'error' => implode("\n", $errors)];
        }
        return ['success' => true];
    }

    /**
     * Delete a manual reference file's vectors unless another activity still uses them.
     *
     * The course collection identifies chunks by filename only, so a same-named
     * file in an AI RAG Material or another assignment shares those vectors.
     *
     * @param int $courseid Course ID
     * @param string $filename Manual reference filename
     * @param int $contextid Context of the assignment doing the cleanup
     * @return bool True if vectors were deleted or intentionally retained
     */
    public static function delete_manual_file_vectors(int $courseid, string $filename, int $contextid): bool {
        if (vector_ownership::is_filename_in_use($courseid, $filename, 0, $contextid)) {
            return true;
        }

        // HTTP 200 means the server processed the delete, even when it found no vectors.
        $result = rag_client::for_component('mod_airagassign', 30)->delete_file($courseid, $filename);
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
     * Tell the teacher when the manual reference file could not be vectorized.
     *
     * Grading stays fail-closed (retrieval is scoped to the file, so an
     * unvectorized file yields no evidence), but the teacher must know why.
     *
     * @param array $result Result of vectorize_manual_files()
     */
    public static function notify_manual_file_vectorization(array $result): void {
        if (empty($result['success'])) {
            \core\notification::warning(get_string('manualfile_vectorize_failed', 'airagassign',
                s($result['error'] ?? 'Unknown error')));
        }
    }
}
