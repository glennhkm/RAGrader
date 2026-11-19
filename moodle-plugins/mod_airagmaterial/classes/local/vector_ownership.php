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

/**
 * Ownership checks for vectors stored in a shared per-course RAG collection.
 *
 * The RAG backend keeps one vector collection per Moodle course and identifies
 * chunks only by their source filename. AI RAG Material activities and AI RAG
 * Assignment manual reference files in the same course therefore share vectors
 * whenever they upload files with the same name (the most recent upload wins).
 *
 * Deleting vectors by filename must not remove chunks that another activity in
 * the course still relies on, so every vector cleanup asks this class first.
 * Per-activity isolation (material_id metadata) is planned for a later cycle.
 *
 * @package    mod_airagmaterial
 * @copyright  2025 Glenn HKM
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */
class vector_ownership {

    /**
     * Whether another activity in the course still uses vectors stored under a filename.
     *
     * @param int $courseid Moodle course ID (the RAG collection namespace).
     * @param string $filename Source filename stored as chunk metadata.
     * @param int $excludematerialid AI RAG Material instance doing the cleanup (0 for none).
     * @param int $excludecontextid Module context doing the cleanup for assignment manual files (0 for none).
     * @return bool True when the vectors must be kept.
     */
    public static function is_filename_in_use(
        int $courseid,
        string $filename,
        int $excludematerialid = 0,
        int $excludecontextid = 0
    ): bool {
        global $DB;

        if ($filename === '') {
            return false;
        }

        $materialsql = "SELECT 1
                          FROM {airagmaterial_files} af
                          JOIN {airagmaterial} am ON am.id = af.materialid
                         WHERE am.course = :courseid
                           AND af.filename = :filename
                           AND af.vectorized = 1
                           AND am.id <> :excludematerialid";
        if ($DB->record_exists_sql($materialsql, [
            'courseid' => $courseid,
            'filename' => $filename,
            'excludematerialid' => $excludematerialid,
        ])) {
            return true;
        }

        // AI RAG Assignment uploads its manual reference file into the same
        // course collection. Query the file table directly so this check works
        // even when mod_airagassign is not installed (no rows will match).
        $manualsql = "SELECT 1
                        FROM {files} f
                        JOIN {context} ctx ON ctx.id = f.contextid AND ctx.contextlevel = :ctxlevel
                        JOIN {course_modules} cm ON cm.id = ctx.instanceid
                       WHERE cm.course = :courseid
                         AND f.component = :component
                         AND f.filearea = :filearea
                         AND f.filename = :filename
                         AND f.contextid <> :excludecontextid";
        return $DB->record_exists_sql($manualsql, [
            'ctxlevel' => CONTEXT_MODULE,
            'courseid' => $courseid,
            'component' => 'mod_airagassign',
            'filearea' => 'manualfile',
            'filename' => $filename,
            'excludecontextid' => $excludecontextid,
        ]);
    }
}
