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
 * Grade page for AI RAG Assignment.
 *
 * Handles both single submission grading and "grade all" for a teacher.
 *
 * @package    mod_airagassign
 * @copyright  2025 Glenn HKM
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

// Dynamic Moodle config path resolver to support symlinked directories and public folder layouts
$configpath = null;
$candidates = [
    __DIR__ . '/../../config.php',
    __DIR__ . '/../../../config.php',
    __DIR__ . '/../moodle/config.php',
];
if (isset($_SERVER['SCRIPT_FILENAME'])) {
    $dir = dirname($_SERVER['SCRIPT_FILENAME']);
    for ($i = 0; $i < 5; $i++) {
        $candidates[] = $dir . '/config.php';
        $dir = dirname($dir);
    }
}
foreach ($candidates as $path) {
    if (file_exists($path)) {
        $configpath = realpath($path);
        break;
    }
}
if ($configpath) {
    require_once($configpath);
} else {
    require_once(__DIR__ . '/../../config.php'); // Fallback
}
require_once($CFG->dirroot . '/mod/airagassign/lib.php');

$id = required_param('id', PARAM_INT);
$submissionid = optional_param('submissionid', 0, PARAM_INT);
$action = optional_param('action', '', PARAM_ALPHA);
$confirmacceptall = optional_param('confirmacceptall', 0, PARAM_BOOL);

$cm = get_coursemodule_from_id('airagassign', $id, 0, false, MUST_EXIST);
$course = get_course($cm->course);
$assign = $DB->get_record('airagassign', ['id' => $cm->instance], '*', MUST_EXIST);

require_login($course, true, $cm);
$context = context_module::instance($cm->id);
require_sesskey();
$returnurl = new moodle_url('/mod/airagassign/view.php', ['id' => $cm->id]);

if ($action === 'revectorize') {
    // ── Re-queue manual reference file vectorization ──────────────────────────
    require_capability('mod/airagassign:manage', $context);
    $queued = \mod_airagassign\local\material_scope::queue_manualfile_vectorization(
        (int)$assign->id, (int)$context->id);
    redirect($returnurl,
        get_string($queued ? 'manualfile_revectorize_queued' : 'manualfile_revectorize_none', 'airagassign'),
        null,
        $queued ? \core\output\notification::NOTIFY_INFO : \core\output\notification::NOTIFY_WARNING);
}

require_capability('mod/airagassign:grade', $context);

if ($action === 'gradeall') {
    // ── Queue bulk-grading background task ────────────────────────────────────
    $submissions = $DB->get_records_select('airagassign_submissions',
        "assignid = :assignid AND status IN ('submitted', 'grading_failed')", ['assignid' => $assign->id]);

    if (empty($submissions)) {
        redirect($returnurl, get_string('nogradablesubmissions', 'airagassign'), null,
            \core\output\notification::NOTIFY_WARNING);
    }

    // Mark and enqueue atomically so a queue failure cannot leave permanent spinners.
    $transaction = $DB->start_delegated_transaction();
    $ids = array_keys($submissions);
    list($insql, $inparams) = $DB->get_in_or_equal($ids, SQL_PARAMS_NAMED);
    $inparams['gradingstartedat'] = time();
    $DB->execute("UPDATE {airagassign_submissions}
                     SET status = 'grading', grading_error = NULL,
                         grading_requestid = NULL, grading_started_at = :gradingstartedat
                   WHERE id $insql", $inparams);

    // Queue a single adhoc task to process them all in the background.
    $task = new \mod_airagassign\task\grade_all_submissions();
    $task->set_custom_data(['assignid' => (int)$assign->id]);
    $task->set_component('mod_airagassign');
    \core\task\manager::queue_adhoc_task($task, true);
    $transaction->allow_commit();

    redirect($returnurl,
        get_string('grading_queued_bulk', 'airagassign', count($submissions)),
        null,
        \core\output\notification::NOTIFY_INFO);

} else if ($action === 'acceptall') {
    // ── Bulk-accept all ai_suggested submissions ──────────────────────────────
    if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST' || !$confirmacceptall) {
        redirect($returnurl,
            get_string('acceptall_confirmation_required', 'airagassign'), null,
            \core\output\notification::NOTIFY_ERROR);
    }

    $pending = $DB->get_records_select('airagassign_submissions',
        "assignid = ? AND status = 'ai_suggested'", [$assign->id]);

    if (empty($pending)) {
        redirect($returnurl, get_string('acceptall_nothing', 'airagassign'), null,
            \core\output\notification::NOTIFY_WARNING);
    }

    $successcount = 0;
    $totalcount   = count($pending);
    $timegraded   = time();
    $transaction  = $DB->start_delegated_transaction();

    foreach ($pending as $sub) {
        // Only accept if there is actually an ai_grade stored.
        if ($sub->ai_grade === null) {
            continue;
        }

        // Promote AI suggestion → final grade.
        $sub->grade      = $sub->ai_grade;
        $sub->feedback   = $sub->ai_feedback ?? '';
        $sub->graded_by  = 'ai_confirmed';
        $sub->status     = 'graded';
        $sub->timegraded = $timegraded;
        $DB->update_record('airagassign_submissions', $sub);

        // Copy ai_score → score and ai_feedback → feedback for every answer row.
        $ansrecs = $DB->get_records('airagassign_answers', ['submissionid' => $sub->id]);
        foreach ($ansrecs as $ar) {
            if ($ar->ai_score !== null) {
                $ar->score    = $ar->ai_score;
                $ar->feedback = $ar->ai_feedback ?? '';
                $DB->update_record('airagassign_answers', $ar);
            }
        }

        // Push to Moodle gradebook.
        airagassign_update_grades($assign, $sub->userid, false);
        $successcount++;
    }

    $transaction->allow_commit();

    $a = new stdClass();
    $a->success = $successcount;
    $a->total   = $totalcount;
    redirect($returnurl,
        get_string('acceptall_complete', 'airagassign', $a),
        null,
        \core\output\notification::NOTIFY_SUCCESS);

} else if ($submissionid) {
    // ── Queue single-submission grading in background ─────────────────────────
    $submission = $DB->get_record('airagassign_submissions',
        ['id' => $submissionid, 'assignid' => $assign->id], '*', MUST_EXIST);

    if (!in_array($submission->status, ['submitted', 'grading_failed'], true)) {
        redirect($returnurl, get_string('alreadysubmitted', 'airagassign'), null,
            \core\output\notification::NOTIFY_WARNING);
    }

    // Mark and enqueue atomically so a queue failure cannot leave a permanent spinner.
    $transaction = $DB->start_delegated_transaction();
    $submission->status = 'grading';
    $submission->grading_error = null;
    $submission->grading_requestid = null;
    $submission->grading_started_at = time();
    $DB->update_record('airagassign_submissions', $submission);

    $task = new \mod_airagassign\task\grade_submission();
    $task->set_custom_data(['submissionid' => (int)$submission->id]);
    $task->set_component('mod_airagassign');
    \core\task\manager::queue_adhoc_task($task, true);
    $transaction->allow_commit();

    $user = $DB->get_record('user', ['id' => $submission->userid]);
    redirect($returnurl,
        get_string('grading_queued_single', 'airagassign', fullname($user)),
        null,
        \core\output\notification::NOTIFY_INFO);
} else {
    redirect($returnurl);
}
