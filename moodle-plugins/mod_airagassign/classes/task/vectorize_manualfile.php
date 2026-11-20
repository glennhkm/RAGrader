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

namespace mod_airagassign\task;

use mod_airagassign\local\material_scope;

/**
 * Adhoc task: vectorize an assignment's manual reference files in the background.
 *
 * Custom data: { assignid: int }. Queued by material_scope::queue_manualfile_vectorization()
 * when the teacher saves the assignment, re-vectorizes the file, after restore, and by the
 * 1.2.0 upgrade. Progress is stored in {airagassign_manualfiles}.
 *
 * @package    mod_airagassign
 * @copyright  2026 RAGrader
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */
class vectorize_manualfile extends \core\task\adhoc_task {
    /**
     * Human-readable task name.
     *
     * @return string
     */
    public function get_name() {
        return get_string('task_vectorize_manualfile', 'mod_airagassign');
    }

    /**
     * Upload the current manual reference files and record their status.
     */
    public function execute() {
        global $DB;

        $assignid = (int)($this->get_custom_data()->assignid ?? 0);
        $assign = $DB->get_record('airagassign', ['id' => $assignid], 'id, course');
        if (!$assign) {
            mtrace("vectorize_manualfile task: assignment $assignid no longer exists — skipping.");
            return;
        }
        $cm = get_coursemodule_from_instance('airagassign', $assign->id, $assign->course, false, IGNORE_MISSING);
        $context = $cm ? \context_module::instance($cm->id, IGNORE_MISSING) : false;
        if (!$context) {
            mtrace("vectorize_manualfile task: course module of assignment $assignid not found — skipping.");
            return;
        }

        $outcome = material_scope::vectorize_manualfiles($assign, (int)$context->id);
        foreach ($outcome['failed'] as $filename => $error) {
            mtrace("vectorize_manualfile task: assignment $assignid file '$filename' failed: $error");
        }
        mtrace('vectorize_manualfile task: assignment ' . $assignid . ': ' . count($outcome['completed']) .
            ' file(s) vectorized, ' . count($outcome['failed']) . ' failed.');
    }
}
