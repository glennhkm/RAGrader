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
 * Adhoc task: grade a single airagassign submission in the background.
 *
 * Custom data: { submissionid: int }
 *
 * @package    mod_airagassign
 * @copyright  2025 Glenn HKM
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

namespace mod_airagassign\task;

defined('MOODLE_INTERNAL') || die();

/**
 * Background AI grading task for a single submission.
 *
 * Queued when a teacher clicks "Grade with AI RAG" on a single submission row.
 * On success the submission status transitions: grading → ai_suggested.
 * On failure it stores a visible error and allows the teacher to retry.
 */
class grade_submission extends \core\task\adhoc_task {

    /**
     * Human-readable task name.
     *
     * @return string
     */
    public function get_name() {
        return 'Grade AI RAG Assignment Submission';
    }

    /**
     * Execute AI grading for one submission.
     */
    public function execute() {
        global $DB, $CFG;

        require_once($CFG->dirroot . '/mod/airagassign/lib.php');

        $data = $this->get_custom_data();
        $submissionid = (int)$data->submissionid;

        $submission = $DB->get_record('airagassign_submissions', ['id' => $submissionid]);
        if (!$submission) {
            mtrace("grade_submission task: submission $submissionid not found — skipping.");
            return;
        }

        if ($submission->status !== 'grading') {
            mtrace("grade_submission task: submission $submissionid status is '{$submission->status}' — not in grading state, skipping.");
            return;
        }

        $assign = $DB->get_record('airagassign', ['id' => $submission->assignid]);
        if (!$assign) {
            mtrace("grade_submission task: assignment {$submission->assignid} not found — skipping.");
            airagassign_record_grading_failure($submissionid, 'Assignment record not found');
            return;
        }

        $cm = get_coursemodule_from_instance('airagassign', $assign->id, $assign->course);
        if (!$cm) {
            airagassign_record_grading_failure($submissionid, 'Course module record not found');
            mtrace("grade_submission task: course module for assignment {$assign->id} not found.");
            return;
        }
        $context = \context_module::instance($cm->id);

        mtrace("Grading submission $submissionid (assign {$assign->id}, user {$submission->userid})...");

        try {
            $result = airagassign_grade_submission($assign, $submission, $context);
        } catch (\Throwable $e) {
            $result = ['success' => false, 'error' => $e->getMessage()];
        }

        if ($result['success']) {
            mtrace("Grading completed for submission $submissionid — status is now 'ai_suggested'.");
        } else {
            $errmsg = $result['error'] ?? 'Unknown error';
            $requestid = $result['requestid'] ?? '';
            airagassign_record_grading_failure($submissionid, $errmsg, $requestid);
            mtrace("Grading FAILED for submission $submissionid: $errmsg" .
                ($requestid !== '' ? " [request ID: $requestid]" : '') . '.');
        }
    }
}
