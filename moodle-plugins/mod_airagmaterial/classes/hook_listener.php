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
 * Hook listener: delete RAG vectors synchronously before a course module is deleted.
 *
 * Moodle calls every function named <plugin>_pre_course_module_delete($cm) before
 * the module instance is removed.  We use this to clean up ChromaDB vectors while
 * the airagmaterial_files rows still exist in the database.
 *
 * @package    mod_airagmaterial
 * @copyright  2025 Glenn HKM
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

/**
 * Called by Moodle core (course/lib.php) immediately before deleting any
 * course module.  We filter for airagmaterial modules and delete their vectors.
 *
 * @param stdClass $cm  The course_modules record of the module about to be deleted.
 */
function mod_airagmaterial_pre_course_module_delete($cm) {
    global $DB;

    // Only act on airagmaterial modules.
    if ($cm->modname !== 'airagmaterial') {
        return;
    }

    require_once(__DIR__ . '/../lib.php');

    $material = $DB->get_record('airagmaterial', ['id' => $cm->instance]);
    if (!$material) {
        return; // Already gone – nothing to clean up.
    }

    // Only call the RAG API if the material was ever vectorized.
    if ($material->vectorize_status !== 'completed') {
        return;
    }

    $trackedfiles = $DB->get_records('airagmaterial_files',
        ['materialid' => $cm->instance], '', 'id, filename');

    foreach ($trackedfiles as $tf) {
        airagmaterial_delete_file_vectors($material->course, $tf->filename);
    }
}
