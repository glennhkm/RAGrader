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
 * View page for AI RAG Assignment.
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

$id = optional_param('id', 0, PARAM_INT);
$a = optional_param('a', 0, PARAM_INT);

if ($id) {
    $cm = get_coursemodule_from_id('airagassign', $id, 0, false, MUST_EXIST);
    $course = get_course($cm->course);
    $assign = $DB->get_record('airagassign', ['id' => $cm->instance], '*', MUST_EXIST);
} else if ($a) {
    $assign = $DB->get_record('airagassign', ['id' => $a], '*', MUST_EXIST);
    $course = get_course($assign->course);
    $cm = get_coursemodule_from_instance('airagassign', $assign->id, $course->id, false, MUST_EXIST);
} else {
    throw new moodle_exception('missingparameter');
}

require_login($course, true, $cm);
$context = context_module::instance($cm->id);
require_capability('mod/airagassign:view', $context);

$cangrade = has_capability('mod/airagassign:grade', $context);
$cansubmit = has_capability('mod/airagassign:submit', $context);

// Trigger view event.
$event = \mod_airagassign\event\course_module_viewed::create([
    'objectid' => $assign->id,
    'context' => $context,
]);
$event->add_record_snapshot('course_modules', $cm);
$event->add_record_snapshot('airagassign', $assign);
$event->trigger();

$PAGE->set_url('/mod/airagassign/view.php', ['id' => $cm->id]);
$PAGE->set_title(format_string($assign->name));
$PAGE->set_heading(format_string($course->fullname));
$PAGE->set_activity_record($assign);

$PAGE->requires->css('/mod/airagassign/styles.css');
echo $OUTPUT->header();
echo html_writer::start_tag('div', ['class' => 'airagassign-main-page']);
echo $OUTPUT->heading(format_string($assign->name));

// Show description.
if (!empty($assign->intro)) {
    echo $OUTPUT->box(format_module_intro('airagassign', $assign, $cm->id), 'generalbox mod_introbox');
}

// ---- Assignment info ----
echo $OUTPUT->heading(get_string('assignmentinfo', 'airagassign'), 3);

$modelabel = ($assign->assignmode === 'quiz')
    ? get_string('mode_quiz', 'airagassign')
    : get_string('mode_essay', 'airagassign');

$now = time();
$isclosed = ($assign->duedate > 0 && $assign->duedate < $now && !$assign->allowlate);
$isnotopen = ($assign->opendate > 0 && $assign->opendate > $now);

echo html_writer::start_tag('table', ['class' => 'table table-sm', 'style' => 'max-width:600px']);
echo html_writer::tag('tr',
    html_writer::tag('th', get_string('assignmentmode', 'airagassign')) .
    html_writer::tag('td', html_writer::span($modelabel, 'badge airag-badge-info'))
);
echo html_writer::tag('tr',
    html_writer::tag('th', get_string('maximumgrade', 'airagassign')) .
    html_writer::tag('td', format_float($assign->maximumgrade, 2))
);

if ($assign->opendate > 0) {
    $opendatestr = userdate($assign->opendate);
    if ($isnotopen) {
        $opendatestr .= ' <span class="badge airag-badge-primary">' . get_string('notavailableyet', 'airagassign', '') . '</span>';
    } else {
        $opendatestr .= ' <span class="badge airag-badge-success">' . get_string('opened', 'airagassign') . '</span>';
    }
    echo html_writer::tag('tr',
        html_writer::tag('th', get_string('opendate', 'airagassign')) .
        html_writer::tag('td', $opendatestr)
    );
}

if ($assign->duedate > 0) {
    $duedatestr = userdate($assign->duedate);
    if ($now < $assign->duedate) {
        $remaining = format_time($assign->duedate - $now);
        $duedatestr .= ' (' . get_string('timeremaining', 'airagassign', $remaining) . ')';
    } else {
        $duedatestr .= ' <span class="badge airag-badge-error">' . get_string('duedatepassed', 'airagassign') . '</span>';
    }
    echo html_writer::tag('tr',
        html_writer::tag('th', get_string('duedate', 'airagassign')) .
        html_writer::tag('td', $duedatestr)
    );
}
echo html_writer::end_tag('table');

// ---- Linked materials ----
$linkedmats = $DB->get_records_sql("
    SELECT m.id, m.name, m.vectorize_status, m.chunks_created, m.documents_loaded
    FROM {airagassign_materials} am
    JOIN {airagmaterial} m ON m.id = am.materialid
    WHERE am.assignid = ?
    ORDER BY m.name
", [$assign->id]);

if (!empty($linkedmats)) {
    echo $OUTPUT->heading(get_string('selectedmaterials', 'airagassign'), 4);
    echo html_writer::start_tag('ul', ['class' => 'list-group mb-3']);
    foreach ($linkedmats as $lm) {
        $statusbadge = ($lm->vectorize_status === 'completed')
            ? html_writer::span('✓ Vectorized (' . $lm->chunks_created . ' chunks)', 'badge airag-badge-success ms-2')
            : html_writer::span('⚠ ' . ucfirst($lm->vectorize_status), 'badge airag-badge-primary ms-2');
        echo html_writer::tag('li', format_string($lm->name) . $statusbadge, ['class' => 'list-group-item']);
    }
    echo html_writer::end_tag('ul');
}

// ---- Manual reference file status (teachers only) ----
$manualfiles = \mod_airagassign\local\material_scope::manual_files($context->id);
if ($cangrade && !empty($manualfiles)) {
    $unreadyfiles = [];
    foreach (\mod_airagassign\local\material_scope::unready_manualfiles($assign->id, $context->id) as $uf) {
        $unreadyfiles[$uf->filename] = $uf;
    }
    $badgeclasses = ['completed' => 'airag-badge-success', 'failed' => 'airag-badge-error'];
    echo $OUTPUT->heading(get_string('manualfile_status', 'airagassign'), 4);
    echo html_writer::start_tag('ul', ['class' => 'list-group mb-3']);
    foreach ($manualfiles as $mf) {
        $uf = $unreadyfiles[$mf->get_filename()] ?? null;
        $mfstatus = $uf ? $uf->status : 'completed';
        $item = s($mf->get_filename()) . html_writer::span(
            \mod_airagassign\local\material_scope::manualfile_status_label($mfstatus),
            'badge ' . ($badgeclasses[$mfstatus] ?? 'airag-badge-primary') . ' ms-2');
        if ($uf && $uf->error_message !== '') {
            $item .= html_writer::tag('div', s($uf->error_message), ['class' => 'small text-danger mt-1']);
        }
        echo html_writer::tag('li', $item, ['class' => 'list-group-item']);
    }
    echo html_writer::end_tag('ul');
    if (has_capability('mod/airagassign:manage', $context)) {
        echo html_writer::start_tag('form', ['method' => 'post', 'class' => 'mb-3',
            'action' => (new moodle_url('/mod/airagassign/grade.php'))->out(false)]);
        foreach (['id' => $cm->id, 'action' => 'revectorize', 'sesskey' => sesskey()] as $name => $value) {
            echo html_writer::empty_tag('input', ['type' => 'hidden', 'name' => $name, 'value' => $value]);
        }
        echo html_writer::tag('button', get_string('manualfile_revectorize', 'airagassign'),
            ['type' => 'submit', 'class' => 'btn btn-secondary btn-sm']);
        echo html_writer::end_tag('form');
    }
}

// ---- Rubric display ----
$criteria = [];
if (($assign->rubricmode ?? '') === 'custom') {
    $criteria = $DB->get_records('airagassign_criteria', ['assignid' => $assign->id], 'sortorder ASC');
}
if (!empty($criteria)) {
    echo $OUTPUT->heading(get_string('rubricinfo', 'airagassign'), 4);
    echo html_writer::start_tag('div', ['class' => 'airag-table-scroll']);
    echo html_writer::start_tag('table', ['class' => 'table table-sm table-bordered', 'style' => 'max-width:700px']);
    echo html_writer::start_tag('thead');
    echo html_writer::tag('tr',
        html_writer::tag('th', get_string('criterionname', 'airagassign')) .
        html_writer::tag('th', get_string('criteriondesc', 'airagassign')) .
        html_writer::tag('th', get_string('criterionmaxscore', 'airagassign'))
    );
    echo html_writer::end_tag('thead');
    echo html_writer::start_tag('tbody');
    foreach ($criteria as $c) {
        echo html_writer::tag('tr',
            html_writer::tag('td', s($c->name)) .
            html_writer::tag('td', s($c->description)) .
            html_writer::tag('td', format_float($c->maxscore, 2))
        );
    }
    echo html_writer::end_tag('tbody');
    echo html_writer::end_tag('table');
    echo html_writer::end_tag('div');
}

// ==================== STUDENT VIEW ====================
if ($cansubmit && !$cangrade) {
    $existingsub = $DB->get_record('airagassign_submissions', ['assignid' => $assign->id, 'userid' => $USER->id]);

    if ($existingsub) {
        // Show submission status.
        echo $OUTPUT->heading(get_string('submissionstatus', 'airagassign'), 3);
        $statusbadge = ($existingsub->status === 'graded')
            ? html_writer::span(get_string('graded', 'airagassign'), 'badge airag-badge-success')
            : html_writer::span(get_string('submitted', 'airagassign'), 'badge airag-badge-info');
        echo html_writer::tag('p', get_string('status', 'airagassign') . ': ' . $statusbadge);
        echo html_writer::tag('p', get_string('submitteddate', 'airagassign') . ': ' . userdate($existingsub->timecreated));

        if ($existingsub->status === 'graded') {
            echo html_writer::tag('p', get_string('grade', 'airagassign') . ': ' .
                html_writer::tag('strong', format_float($existingsub->grade, 2) . ' / ' . format_float($assign->maximumgrade, 2)));

            $resulturl = new moodle_url('/mod/airagassign/view_result.php', [
                'id' => $cm->id,
                'submissionid' => $existingsub->id,
            ]);
            echo html_writer::link($resulturl, get_string('viewresult', 'airagassign'), ['class' => 'btn btn-airag-primary']);
        }

        // Show submitted answers.
        echo $OUTPUT->heading(($assign->assignmode === 'quiz') ? get_string('youranswer', 'airagassign') : get_string('youressay', 'airagassign'), 4);
        $answers = $DB->get_records('airagassign_answers', ['submissionid' => $existingsub->id]);

        if ($assign->assignmode === 'quiz') {
            $questions = $DB->get_records('airagassign_questions', ['assignid' => $assign->id], 'sortorder ASC');
            $answermap = [];
            foreach ($answers as $ans) {
                $answermap[$ans->questionid] = $ans;
            }
            $qnum = 1;
            foreach ($questions as $q) {
                $ans = $answermap[$q->id] ?? null;
                echo html_writer::tag('div',
                    html_writer::tag('strong', get_string('questiontext', 'airagassign', $qnum)) .
                    html_writer::tag('p', s($q->questiontext)) .
                    html_writer::tag('p', html_writer::tag('em', get_string('youranswer', 'airagassign') . ': ') .
                        s($ans ? $ans->answertext : '-')) .
                    ($existingsub->status === 'graded' && $ans && $ans->score !== null
                        ? html_writer::tag('p', get_string('score', 'airagassign') . ': ' .
                            html_writer::tag('strong', format_float($ans->score, 2)) .
                            ($ans->feedback ? html_writer::empty_tag('br') . get_string('feedback', 'airagassign') . ': ' . s($ans->feedback) : ''))
                        : ''),
                    ['class' => 'card card-body mb-2']
                );
                $qnum++;
            }
        } else {
            $answer = reset($answers);
            if ($answer) {
                echo html_writer::tag('div', nl2br(s($answer->answertext)), ['class' => 'card card-body']);
            }
        }
    } else if ($isclosed) {
        // Closed, no submission.
        echo $OUTPUT->notification(get_string('notallowedsinceclosed', 'airagassign'), 'warning');
    } else if ($isnotopen) {
        // Not yet open.
        $opendatestr = userdate($assign->opendate);
        echo $OUTPUT->notification(get_string('notavailableyet', 'airagassign', $opendatestr), 'warning');
    } else {
        // Show submit link — but only if at least one linked material is vectorized or a manual file is uploaded.
        $fs = get_file_storage();
        $manualfiles = $fs->get_area_files($context->id, 'mod_airagassign', 'manualfile', 0, 'id', false);
        $hasmanualfile = !empty($manualfiles);

        $validmaterialcount = $DB->count_records_sql(
            "SELECT COUNT(*) FROM {airagassign_materials} am
               JOIN {airagmaterial} m ON m.id = am.materialid
              WHERE am.assignid = :assignid AND m.vectorize_status = 'completed'",
            ['assignid' => $assign->id]
        );
        if ($validmaterialcount == 0 && !$hasmanualfile) {
            echo $OUTPUT->notification(get_string('nomaterialsavailable', 'airagassign'), 'warning');
        } else {
            $submiturl = new moodle_url('/mod/airagassign/submit.php', ['id' => $cm->id]);
            echo html_writer::link($submiturl, get_string('submitanswers', 'airagassign'), ['class' => 'btn btn-airag-primary btn-lg']);
        }
    }
}

// ==================== TEACHER VIEW ====================
if ($cangrade) {
    echo $OUTPUT->heading(get_string('allsubmissions', 'airagassign'), 3);

    // Count enrolled students.
    $enrolledusers = get_enrolled_users($context, 'mod/airagassign:submit');
    $totalstudents = count($enrolledusers);
    $submissions = $DB->get_records('airagassign_submissions', ['assignid' => $assign->id]);
    $submittedcount = count($submissions);

    $a = new stdClass();
    $a->submitted = $submittedcount;
    $a->total = $totalstudents;
    echo html_writer::tag('p', get_string('submittedcount', 'airagassign', $a), ['class' => 'text-muted']);

    if (!empty($submissions)) {
        echo html_writer::start_tag('div', ['class' => 'table-responsive']);
        echo html_writer::start_tag('table', ['class' => 'table table-striped']);
        echo html_writer::start_tag('thead');
        echo html_writer::tag('tr',
            html_writer::tag('th', get_string('student', 'airagassign')) .
            html_writer::tag('th', get_string('submitteddate', 'airagassign')) .
            html_writer::tag('th', get_string('status', 'airagassign')) .
            html_writer::tag('th', get_string('grade', 'airagassign')) .
            html_writer::tag('th', get_string('actions', 'airagassign'))
        );
        echo html_writer::end_tag('thead');
        echo html_writer::start_tag('tbody');

        foreach ($submissions as $sub) {
            $user = $DB->get_record('user', ['id' => $sub->userid]);
            $fullname = fullname($user);

            // Status badge.
            if ($sub->status === 'graded') {
                $statusbadge = html_writer::span(
                    get_string('graded', 'airagassign'), 'badge airag-badge-success');
            } else if ($sub->status === 'ai_suggested') {
                $statusbadge = html_writer::span(
                    get_string('ai_suggestion_pending', 'airagassign'),
                    'badge airag-badge-primary');
            } else if ($sub->status === 'grading') {
                $statusbadge =
                    html_writer::tag('span', '', ['class' => 'spinner-border spinner-border-sm me-1', 'role' => 'status', 'aria-hidden' => 'true']) .
                    html_writer::span(get_string('grading', 'airagassign'), 'badge airag-badge-primary ms-1');
            } else if ($sub->status === 'grading_failed') {
                $statusbadge = html_writer::span(
                    get_string('status_grading_failed', 'airagassign'), 'badge airag-badge-error');
                if (!empty($sub->grading_error)) {
                    $statusbadge .= html_writer::tag('div', s($sub->grading_error),
                        ['class' => 'airag-grading-error']);
                }
                if (!empty($sub->grading_requestid)) {
                    $statusbadge .= html_writer::tag('code',
                        get_string('grading_requestid', 'airagassign') . ': ' . s($sub->grading_requestid),
                        ['class' => 'airag-request-id']);
                }
            } else {
                $statusbadge = html_writer::span(
                    get_string('notgraded', 'airagassign'), 'badge airag-badge-muted');
            }

            // Grade display.
            if ($sub->status === 'graded') {
                $gradestr = format_float($sub->grade, 2) . ' / ' .
                    format_float($assign->maximumgrade, 2);
            } else if ($sub->status === 'ai_suggested') {
                $gradestr = html_writer::tag('em',
                    '(' . get_string('aisuggested_grade', 'airagassign') . ': ' .
                    format_float($sub->ai_grade, 2) . ')',
                    ['class' => 'text-muted small']);
            } else {
                $gradestr = '-';
            }

            // Action buttons.
            $actions = '';
            if ($sub->status === 'graded') {
                $resulturl = new moodle_url('/mod/airagassign/view_result.php', [
                    'id' => $cm->id, 'submissionid' => $sub->id,
                ]);
                $actions .= html_writer::link($resulturl,
                    get_string('viewresult', 'airagassign'),
                    ['class' => 'btn btn-sm btn-airag-outline-info me-1']);
                $editurl = new moodle_url('/mod/airagassign/grade_manual.php', [
                    'id' => $cm->id, 'submissionid' => $sub->id,
                ]);
                $actions .= html_writer::link($editurl,
                    get_string('editgrade', 'airagassign'),
                    ['class' => 'btn btn-sm btn-airag-outline-secondary']);

            } else if ($sub->status === 'ai_suggested') {
                $reviewurl = new moodle_url('/mod/airagassign/grade_review.php', [
                    'id' => $cm->id, 'submissionid' => $sub->id,
                ]);
                $actions .= html_writer::link($reviewurl,
                    get_string('reviewaisuggestion', 'airagassign'),
                    ['class' => 'btn btn-sm btn-airag-primary me-1']);
                $manualurl = new moodle_url('/mod/airagassign/grade_manual.php', [
                    'id' => $cm->id, 'submissionid' => $sub->id,
                ]);
                $actions .= html_writer::link($manualurl,
                    get_string('grademanually', 'airagassign'),
                    ['class' => 'btn btn-sm btn-airag-outline-secondary']);

            } else if ($sub->status === 'grading') {
                $actions = html_writer::span(get_string('grading', 'airagassign'), 'text-muted small');

            } else {
                // Submitted or failed: offer AI grading/retry and manual grading.
                $gradeaiurl = new moodle_url('/mod/airagassign/grade.php', [
                    'id'           => $cm->id,
                    'submissionid' => $sub->id,
                    'sesskey'      => sesskey(),
                ]);
                $actions .= html_writer::link($gradeaiurl,
                    get_string($sub->status === 'grading_failed' ? 'retrygrading' : 'gradewithairag', 'airagassign'),
                    ['class' => 'btn btn-sm btn-airag-info me-1']);
                $manualurl = new moodle_url('/mod/airagassign/grade_manual.php', [
                    'id' => $cm->id, 'submissionid' => $sub->id,
                ]);
                $actions .= html_writer::link($manualurl,
                    get_string('grademanually', 'airagassign'),
                    ['class' => 'btn btn-sm btn-airag-outline-secondary']);
            }

            echo html_writer::start_tag('tr');
            echo html_writer::tag('td', $fullname);
            echo html_writer::tag('td', userdate($sub->timecreated));
            echo html_writer::tag('td', $statusbadge);
            echo html_writer::tag('td', $gradestr);
            echo html_writer::tag('td',
                html_writer::tag('div', $actions, ['class' => 'airag-table-actions']));
            echo html_writer::end_tag('tr');
        }

        echo html_writer::end_tag('tbody');
        echo html_writer::end_tag('table');
        echo html_writer::end_tag('div');
    } else {
        echo $OUTPUT->notification(get_string('nosubmissions', 'airagassign'), 'info');
    }

    // "Grade All" button.
    $ungradedcount = $DB->count_records_select('airagassign_submissions',
        "assignid = :assignid AND status IN ('submitted', 'grading_failed')", ['assignid' => $assign->id]);
    $aisuggestedcount = $DB->count_records_select('airagassign_submissions',
        "assignid = ? AND status = 'ai_suggested'", [$assign->id]);
    $gradingcount = $DB->count_records_select('airagassign_submissions',
        "assignid = ? AND status = 'grading'", [$assign->id]);

    // ── Polling banner ────────────────────────────────────────────
    $isgradingbusy = ($gradingcount > 0);
    echo html_writer::tag('div',
        html_writer::tag('span', '', ['class' => 'spinner-border spinner-border-sm me-2', 'role' => 'status', 'aria-hidden' => 'true']) .
        html_writer::tag('strong', get_string('grading_processing_title', 'airagassign')) .
        html_writer::tag('span',
            ' (' . $gradingcount . ' ' . get_string('submissions', 'core_grades') . ') — ' .
            get_string('queue_navigate_away', 'airagassign'),
            ['id' => 'airag-grading-count', 'class' => 'ms-1']),
        [
            'id'    => 'airag-grading-busy-banner',
            'class' => 'alert alert-info airag-status-banner mb-3 mt-3' . ($isgradingbusy ? '' : ' d-none'),
            'style' => $isgradingbusy ? '' : 'display:none!important',
        ]
    );

    echo html_writer::start_tag('div', ['class' => 'airag-action-row mt-3']);
    if ($ungradedcount > 0) {
        $gradeallurl = new moodle_url('/mod/airagassign/grade.php', [
            'id'      => $cm->id,
            'action'  => 'gradeall',
            'sesskey' => sesskey(),
        ]);
        echo html_writer::link($gradeallurl,
            get_string('gradingall', 'airagassign') . ' (' . $ungradedcount . ')',
            ['class' => 'btn btn-airag-info btn-lg']);
    }
    if ($aisuggestedcount > 0) {
        // Warning alert + button to open the theme-independent confirmation dialog.
        $acceptallurl = new moodle_url('/mod/airagassign/grade.php');
        echo html_writer::start_tag('div',
            ['class' => 'airag-banner airag-banner-primary airag-pending-actions mb-0']);
        echo html_writer::tag('span',
            get_string('ai_suggestions_pending', 'airagassign', $aisuggestedcount));
        echo html_writer::tag('button',
            get_string('acceptall_ai', 'airagassign'),
            [
                'type' => 'button',
                'class' => 'btn btn-sm btn-airag-error ms-auto',
                'id' => 'airag-acceptall-open',
                'aria-haspopup' => 'dialog',
                'aria-controls' => 'airag-acceptall-overlay',
            ]);
        echo html_writer::end_tag('div');

        // The dialog is implemented without Bootstrap JS so it works across
        // Moodle 4.5 themes that ship different Bootstrap generations.
        echo html_writer::start_tag('div', [
            'class' => 'airag-confirm-overlay',
            'id' => 'airag-acceptall-overlay',
            'hidden' => 'hidden',
            'aria-hidden' => 'true',
        ]);
        echo html_writer::start_tag('div', [
            'class' => 'airag-confirm-dialog',
            'role' => 'dialog',
            'aria-modal' => 'true',
            'aria-labelledby' => 'airag-acceptall-title',
            'aria-describedby' => 'airag-acceptall-description',
            'tabindex' => '-1',
        ]);
        echo html_writer::start_tag('div', ['class' => 'airag-confirm-header']);
        echo html_writer::tag('h3',
            get_string('acceptall_ai_confirm_title', 'airagassign'),
            ['id' => 'airag-acceptall-title']);
        echo html_writer::tag('button', '&#x00D7;', [
            'type' => 'button',
            'class' => 'airag-confirm-close',
            'id' => 'airag-acceptall-close',
            'aria-label' => get_string('close', 'core'),
        ]);
        echo html_writer::end_tag('div');

        echo html_writer::start_tag('form', [
            'method' => 'post',
            'action' => $acceptallurl,
            'id' => 'airag-acceptall-form',
        ]);
        echo html_writer::empty_tag('input', [
            'type' => 'hidden', 'name' => 'id', 'value' => $cm->id,
        ]);
        echo html_writer::empty_tag('input', [
            'type' => 'hidden', 'name' => 'action', 'value' => 'acceptall',
        ]);
        echo html_writer::empty_tag('input', [
            'type' => 'hidden', 'name' => 'sesskey', 'value' => sesskey(),
        ]);
        echo html_writer::start_tag('div', ['class' => 'airag-confirm-body']);
        echo html_writer::tag('div',
            get_string('acceptall_ai_confirm_body', 'airagassign', $aisuggestedcount),
            ['class' => 'airag-banner airag-banner-error',
             'id' => 'airag-acceptall-description']);
        echo html_writer::start_tag('div', ['class' => 'airag-confirm-check']);
        echo html_writer::empty_tag('input', [
            'type' => 'checkbox',
            'id' => 'airag-acceptall-confirm-check',
            'name' => 'confirmacceptall',
            'value' => '1',
            'required' => 'required',
        ]);
        echo html_writer::tag('label',
            get_string('acceptall_ai_confirm_check', 'airagassign'),
            ['for' => 'airag-acceptall-confirm-check']);
        echo html_writer::end_tag('div');
        echo html_writer::end_tag('div');

        echo html_writer::start_tag('div', ['class' => 'airag-confirm-actions']);
        echo html_writer::tag('button', get_string('cancel', 'core'), [
            'type' => 'button',
            'class' => 'btn btn-airag-outline-secondary',
            'id' => 'airag-acceptall-cancel',
        ]);
        echo html_writer::tag('button', get_string('acceptall_ai', 'airagassign'), [
            'type' => 'submit',
            'class' => 'btn btn-airag-error',
            'id' => 'airag-acceptall-confirm-btn',
            'disabled' => 'disabled',
        ]);
        echo html_writer::end_tag('div');
        echo html_writer::end_tag('form');
        echo html_writer::end_tag('div');
        echo html_writer::end_tag('div');

        echo <<<'JS'
<script>
(function () {
    'use strict';
    var opener = document.getElementById('airag-acceptall-open');
    var overlay = document.getElementById('airag-acceptall-overlay');
    var dialog = overlay ? overlay.querySelector('.airag-confirm-dialog') : null;
    var closeButton = document.getElementById('airag-acceptall-close');
    var cancelButton = document.getElementById('airag-acceptall-cancel');
    var checkbox = document.getElementById('airag-acceptall-confirm-check');
    var confirmButton = document.getElementById('airag-acceptall-confirm-btn');
    var form = document.getElementById('airag-acceptall-form');

    if (!opener || !overlay || !dialog || !closeButton || !cancelButton ||
            !checkbox || !confirmButton || !form) {
        return;
    }

    function reset() {
        checkbox.checked = false;
        confirmButton.disabled = true;
        confirmButton.removeAttribute('aria-busy');
    }

    function openDialog() {
        reset();
        overlay.hidden = false;
        overlay.setAttribute('aria-hidden', 'false');
        document.body.classList.add('airag-modal-open');
        closeButton.focus();
    }

    function closeDialog() {
        overlay.hidden = true;
        overlay.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('airag-modal-open');
        reset();
        opener.focus();
    }

    opener.addEventListener('click', openDialog);
    closeButton.addEventListener('click', closeDialog);
    cancelButton.addEventListener('click', closeDialog);
    overlay.addEventListener('click', function (event) {
        if (event.target === overlay) {
            closeDialog();
        }
    });
    checkbox.addEventListener('change', function () {
        confirmButton.disabled = !checkbox.checked;
    });
    document.addEventListener('keydown', function (event) {
        if (overlay.hidden) {
            return;
        }
        if (event.key === 'Escape') {
            event.preventDefault();
            closeDialog();
            return;
        }
        if (event.key === 'Tab') {
            var focusable = dialog.querySelectorAll(
                'button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'
            );
            if (!focusable.length) {
                event.preventDefault();
                dialog.focus();
                return;
            }
            var first = focusable[0];
            var last = focusable[focusable.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        }
    });
    form.addEventListener('submit', function (event) {
        if (!checkbox.checked) {
            event.preventDefault();
            checkbox.focus();
            return;
        }
        confirmButton.disabled = true;
        confirmButton.setAttribute('aria-busy', 'true');
    });
})();
</script>
JS;
    }
    echo html_writer::end_tag('div');
}

echo html_writer::end_tag('div'); // airagassign-main-page.

// ── Polling JS: auto-refresh when grading tasks are running ──────────────────
$gradingstatusurl = (new moodle_url('/mod/airagassign/grading_status.php', ['id' => $cm->id]))->out(false);
$cangrade_js = $cangrade ? 'true' : 'false';
$isgradingbusy_js = isset($isgradingbusy) && $isgradingbusy ? 'true' : 'false';
echo <<<HTML
<script>
(function () {
    if ({$cangrade_js} !== true) return;
    var busy   = {$isgradingbusy_js};
    var banner = document.getElementById('airag-grading-busy-banner');

    function showBanner(show) {
        if (!banner) return;
        if (show) {
            banner.style.removeProperty('display');
            banner.classList.remove('d-none');
        } else {
            banner.style.display = 'none';
        }
    }

    if (!busy) return; // no grading in progress — nothing to poll

    showBanner(true);

    var interval = setInterval(function () {
        fetch('{$gradingstatusurl}', {credentials: 'same-origin'})
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.busy) {
                    clearInterval(interval);
                    // Reload so the table shows updated statuses (ai_suggested/submitted).
                    window.location.reload();
                }
            })
            .catch(function () { /* network error: keep polling */ });
    }, 5000);
})();
</script>
HTML;

echo $OUTPUT->footer();
