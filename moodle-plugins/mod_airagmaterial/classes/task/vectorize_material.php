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
 * Adhoc task: vectorize a single airagmaterial instance in the background.
 *
 * Custom data: { materialid: int, contextid: int }
 *
 * @package    mod_airagmaterial
 * @copyright  2025 Glenn HKM
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

namespace mod_airagmaterial\task;

defined('MOODLE_INTERNAL') || die();

/**
 * Background vectorization task for a single airagmaterial instance.
 *
 * Queued by airagmaterial_queue_vectorize_task() whenever a teacher creates/
 * updates a material module, or manually clicks "Re-vectorize".
 * The actual API call (airagmaterial_vectorize_files) is executed here so the
 * web request returns instantly and the teacher does not have to wait.
 */
class vectorize_material extends \core\task\adhoc_task {

    /**
     * Human-readable task name shown in Moodle's admin task log.
     *
     * @return string
     */
    public function get_name() {
        return get_string('task_vectorize', 'mod_airagmaterial');
    }

    /**
     * Execute the vectorization task.
     *
     * Reads materialid + contextid from custom data, calls the RAG server, and
     * updates the DB status accordingly.
     */
    public function execute() {
        global $DB, $CFG;

        require_once($CFG->dirroot . '/mod/airagmaterial/lib.php');

        $data = $this->get_custom_data();
        $materialid = (int)$data->materialid;
        $contextid  = (int)$data->contextid;

        // Load the material record.
        $material = $DB->get_record('airagmaterial', ['id' => $materialid]);
        if (!$material) {
            mtrace("vectorize_material task: material $materialid not found — skipping.");
            return;
        }

        // Bail if another process already handled it (e.g., duplicate task).
        if ($material->vectorize_status !== 'queued' && $material->vectorize_status !== 'processing') {
            mtrace("vectorize_material task: material $materialid status is '{$material->vectorize_status}' — not in queued state, skipping.");
            return;
        }

        $context = \context::instance_by_id($contextid, IGNORE_MISSING);
        if (!$context) {
            mtrace("vectorize_material task: context $contextid not found — marking failed.");
            $DB->set_field('airagmaterial', 'vectorize_status', 'failed', ['id' => $materialid]);
            $DB->set_field('airagmaterial', 'vectorize_error', 'Context not found during background processing.', ['id' => $materialid]);
            return;
        }

        mtrace("Starting vectorization for material $materialid ('{$material->name}')...");

        $result = airagmaterial_vectorize_files($material, $context);

        if ($result['success']) {
            mtrace("Vectorization completed: {$result['chunks']} chunks from {$result['documents']} documents.");
        } else {
            $errs = implode(', ', $result['errors'] ?? ['Unknown error']);
            mtrace("Vectorization finished with errors: $errs");
        }
    }
}
