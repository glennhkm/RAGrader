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
 * Adhoc task: grade all pending submissions for one airagassign in the background.
 *
 * Custom data: { assignid: int }
 *
 * @package    mod_airagassign
 * @copyright  2025 Glenn HKM
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

namespace mod_airagassign\task;

use mod_airagassign\local\grading_service;

defined('MOODLE_INTERNAL') || die();

/**
 * Background bulk AI grading task.
 *
 * Queued when a teacher clicks "Grade All with AI RAG".
 * All submissions whose status was set to 'grading' before the task ran are
 * processed sequentially; failures remain visible and can be retried.
 */
class grade_all_submissions extends \core\task\adhoc_task {

    /**
     * Human-readable task name.
     *
     * @return string
     */
    public function get_name() {
        return 'Grade All AI RAG Assignment Submissions';
    }

    /**
     * Execute bulk AI grading.
     */
    public function execute() {
        global $DB, $CFG;

        require_once($CFG->dirroot . '/mod/airagassign/lib.php');
        $service = new grading_service();

        $data = $this->get_custom_data();
        $assignid = (int)$data->assignid;

        $assign = $DB->get_record('airagassign', ['id' => $assignid]);
        if (!$assign) {
            mtrace("grade_all_submissions task: assignment $assignid not found — skipping.");
            return;
        }

        $submissions = $DB->get_records_select(
            'airagassign_submissions',
            "assignid = :assignid AND status = 'grading'",
            ['assignid' => $assignid]
        );

        if (empty($submissions)) {
            mtrace("grade_all_submissions task: no submissions in 'grading' state for assign $assignid — skipping.");
            return;
        }

        $cm = get_coursemodule_from_instance('airagassign', $assign->id, $assign->course);
        if (!$cm) {
            foreach ($submissions as $sub) {
                grading_service::record_failure((int)$sub->id, 'Course module record not found');
            }
            mtrace("grade_all_submissions task: course module for assignment $assignid not found.");
            return;
        }
        $context = \context_module::instance($cm->id);

        $total   = count($submissions);
        $success = 0;

        mtrace("Bulk grading $total submission(s) for assignment $assignid...");

        foreach ($submissions as $sub) {
            mtrace("  Grading submission {$sub->id} (user {$sub->userid})...");
            try {
                $result = $service->grade_submission($assign, $sub, $context);
            } catch (\Throwable $e) {
                $result = ['success' => false, 'error' => $e->getMessage()];
            }
            if ($result['success']) {
                $success++;
                mtrace("  Done.");
            } else {
                $errmsg = (string)($result['error'] ?? 'Unknown error');
                $requestid = (string)($result['requestid'] ?? '');
                grading_service::record_failure((int)$sub->id, $errmsg, $requestid);
                mtrace("  Failed: $errmsg" .
                    ($requestid !== '' ? " [request ID: $requestid]" : '') . '.');
            }
        }

        mtrace("Bulk grading complete: $success/$total succeeded.");
    }
}
