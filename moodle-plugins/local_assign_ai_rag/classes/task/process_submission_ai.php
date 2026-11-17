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

namespace local_assign_ai_rag\task;

defined('MOODLE_INTERNAL') || die();

global $CFG;
require_once($CFG->dirroot . '/mod/assign/locallib.php');
require_once($CFG->dirroot . '/local/assign_ai_rag/locallib.php');

use core\task\adhoc_task;

/**
 * Ad-hoc task to process AI submission for an assignment using RAG.
 *
 * @package    local_assign_ai_rag
 * @category   task
 * @copyright  2025 Glenn H. K. M.
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */
class process_submission_ai extends adhoc_task {
    /**
     * Execute the task.
     *
     * Expected custom data:
     *  - userid (int)
     *  - cmid (int)
     *
     * @return void
     */
    public function execute(): void {
        global $CFG;

        $data = $this->get_custom_data();
        if (empty($data->userid) || empty($data->cmid)) {
            return;
        }

        try {
            $cmid = (int)$data->cmid;
            $userid = (int)$data->userid;

            $cm = get_coursemodule_from_id('assign', $cmid, 0, false, MUST_EXIST);
            $course = get_course($cm->course);
            $context = \context_module::instance($cmid);

            $assign = new \assign($context, $cm, $course);

            $submission = new \local_assign_ai_rag\assign_submission($userid, $assign);
            $submission->process_submission_ai();
        } catch (\Exception $e) {
            mtrace('Error processing RAG AI submission: ' . $e->getMessage());
        }
    }

    /**
     * Get a descriptive name for this task (shown in admin UI).
     *
     * @return string
     */
    public function get_name() {
        return get_string('taskprocesssubmission', 'local_assign_ai_rag');
    }
}
