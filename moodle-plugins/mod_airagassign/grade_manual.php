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
 * Human-in-the-loop: Teacher grades a submission manually (without AI).
 *
 * Also used to edit an already-graded submission.
 * When status is 'ai_suggested' a banner is shown offering a link to
 * grade_review.php so the teacher can optionally review the AI suggestion first.
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

$id           = required_param('id', PARAM_INT);
$submissionid = required_param('submissionid', PARAM_INT);

$cm     = get_coursemodule_from_id('airagassign', $id, 0, false, MUST_EXIST);
$course = get_course($cm->course);
$assign = $DB->get_record('airagassign', ['id' => $cm->instance], '*', MUST_EXIST);

require_login($course, true, $cm);
$context = context_module::instance($cm->id);
require_capability('mod/airagassign:grade', $context);

$submission = $DB->get_record('airagassign_submissions',
    ['id' => $submissionid, 'assignid' => $assign->id], '*', MUST_EXIST);
$user = $DB->get_record('user', ['id' => $submission->userid], '*', MUST_EXIST);

$returnurl = new moodle_url('/mod/airagassign/view.php', ['id' => $cm->id]);

$PAGE->set_url('/mod/airagassign/grade_manual.php',
    ['id' => $cm->id, 'submissionid' => $submissionid]);
$PAGE->set_title(get_string('grademanually', 'airagassign') . ': ' . fullname($user));
$PAGE->set_heading(format_string($course->fullname));

// ============================================================
// POST HANDLER — save manual grade
// ============================================================
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    require_sesskey();

    $finalgrade    = required_param('finalgrade', PARAM_FLOAT);
    $finalfeedback = optional_param('finalfeedback', '', PARAM_TEXT);
    $teachernote   = optional_param('teacher_note', '', PARAM_TEXT);

    $finalgrade = max(0.0, min((float)$assign->maximumgrade, $finalgrade));

    $submission->grade        = round($finalgrade, 2);
    $submission->feedback     = $finalfeedback;
    $submission->graded_by    = 'teacher';
    $submission->teacher_note = $teachernote;
    $submission->status       = 'graded';
    $submission->timegraded   = time();
    $DB->update_record('airagassign_submissions', $submission);

    if ($assign->assignmode === 'quiz') {
        $ansrecs   = $DB->get_records('airagassign_answers',
            ['submissionid' => $submission->id]);
        $questions = $DB->get_records('airagassign_questions',
            ['assignid' => $assign->id], 'sortorder ASC');
        $numq      = count($questions);
        $gradeperq = $numq > 0 ? (float)$assign->maximumgrade / $numq : 0;

        foreach ($ansrecs as $ar) {
            $s = optional_param('answer_score_' . $ar->id, null, PARAM_FLOAT);
            $f = optional_param('answer_fb_' . $ar->id, '', PARAM_TEXT);
            if ($s !== null) {
                $ar->score    = max(0.0, min($gradeperq, (float)$s));
                $ar->feedback = $f;
                $DB->update_record('airagassign_answers', $ar);
            }
        }
    } else {
        // Essay: mirror grade to the single answer row.
        $ar = $DB->get_record('airagassign_answers',
            ['submissionid' => $submission->id]);
        if ($ar) {
            $ar->score    = $finalgrade;
            $ar->feedback = $finalfeedback;
            $DB->update_record('airagassign_answers', $ar);
        }
    }

    airagassign_update_grades($assign, $submission->userid, false);

    redirect($returnurl,
        get_string('gradingsuccess', 'airagassign', fullname($user)),
        null, \core\output\notification::NOTIFY_SUCCESS);
}

// ============================================================
// GET — display manual grading form
// ============================================================
$PAGE->requires->css('/mod/airagassign/styles.css');
echo $OUTPUT->header();
echo html_writer::start_tag('div', ['class' => 'airagassign-workflow-page']);
echo $OUTPUT->heading(get_string('grademanually', 'airagassign') . ': ' . fullname($user));

// Navigation.
echo html_writer::start_tag('nav', ['class' => 'airag-navigation', 'aria-label' => get_string('actions')]);
echo html_writer::link($returnurl,
    '&larr; ' . get_string('backtoassignment', 'airagassign'),
    ['class' => 'btn btn-airag-outline-secondary airag-back-btn']);
echo html_writer::end_tag('nav');

// If AI suggestion is available, show a hint banner.
if ($submission->status === 'ai_suggested') {
    $reviewurl = new moodle_url('/mod/airagassign/grade_review.php',
        ['id' => $cm->id, 'submissionid' => $submission->id]);
    echo html_writer::tag('div',
        get_string('aisuggestion_available', 'airagassign') . ' &mdash; ' .
        html_writer::link($reviewurl,
            get_string('reviewaisuggestion', 'airagassign'),
            ['class' => 'fw-semibold text-airag-info']),
        ['class' => 'airag-banner airag-banner-info']
    );
}

echo html_writer::start_tag('div', ['class' => 'airag-two-column']);

// ── LEFT: student answers + rubric reference ──────────────────────────────────
echo html_writer::start_tag('section', ['class' => 'airag-column']);
echo html_writer::tag('h6', get_string('studentsubmission', 'airagassign'),
    ['class' => 'airag-section-title']);

$answers = $DB->get_records('airagassign_answers', ['submissionid' => $submission->id]);

if ($assign->assignmode === 'quiz') {
    $questions = $DB->get_records('airagassign_questions',
        ['assignid' => $assign->id], 'sortorder ASC');
    $answermap = [];
    foreach ($answers as $ans) {
        $answermap[$ans->questionid] = $ans;
    }
    $qnum = 1;
    foreach ($questions as $q) {
        $ans = $answermap[$q->id] ?? null;
        echo html_writer::start_tag('div',
            ['class' => 'card mb-2 airag-accent-card']);
        echo html_writer::tag('div',
            html_writer::tag('strong', 'Q' . $qnum . ': ' . s($q->questiontext)),
            ['class' => 'card-header py-2 bg-light']);
        echo html_writer::tag('div',
            html_writer::tag('p', nl2br(s($ans ? $ans->answertext : '-')),
                ['class' => 'mb-0 small']),
            ['class' => 'card-body py-2']);
        echo html_writer::end_tag('div');
        $qnum++;
    }
} else {
    $answer = reset($answers);
    echo html_writer::start_tag('div', ['class' => 'card']);
    echo html_writer::start_tag('div', ['class' => 'card-body']);
    echo html_writer::tag('div', nl2br(s($answer ? $answer->answertext : '-')),
        ['style' => 'max-height:450px;overflow-y:auto;font-size:.9rem']);
    echo html_writer::end_tag('div');
    echo html_writer::end_tag('div');
}

// Rubric reference.
$criteria = $DB->get_records('airagassign_criteria',
    ['assignid' => $assign->id], 'sortorder ASC');
if (!empty($criteria)) {
    echo html_writer::tag('h6', '' . get_string('rubricinfo', 'airagassign'),
        ['class' => 'mt-3 mb-1']);
    echo html_writer::start_tag('div', ['class' => 'airag-table-scroll']);
    echo html_writer::start_tag('table',
        ['class' => 'table table-sm table-bordered small']);
    echo html_writer::tag('tr',
        html_writer::tag('th', get_string('criterionname', 'airagassign')) .
        html_writer::tag('th', get_string('criteriondesc', 'airagassign')) .
        html_writer::tag('th', get_string('criterionmaxscore', 'airagassign'))
    );
    foreach ($criteria as $c) {
        echo html_writer::tag('tr',
            html_writer::tag('td', s($c->name)) .
            html_writer::tag('td', s($c->description)) .
            html_writer::tag('td', format_float($c->maxscore, 2))
        );
    }
    echo html_writer::end_tag('table');
    echo html_writer::end_tag('div');
}

echo html_writer::end_tag('section'); // Student submission column.

// ── RIGHT: grading form ───────────────────────────────────────────────────────
echo html_writer::start_tag('section', ['class' => 'airag-column']);
echo html_writer::tag('h6', get_string('gradingform', 'airagassign'),
    ['class' => 'airag-section-title']);

$formurl           = new moodle_url('/mod/airagassign/grade_manual.php',
    ['id' => $cm->id, 'submissionid' => $submission->id]);
// format_float() uses locale decimal separator (e.g. "10,00" in ID locale).
// HTML number inputs MUST use "." — use sprintf for value/min/max/data-max attrs.
$maxgradeformatted = format_float($assign->maximumgrade, 2); // display only
$maxgrade_inp      = sprintf('%.2f', (float)$assign->maximumgrade); // input attrs

echo html_writer::start_tag('form', ['method' => 'post', 'action' => $formurl]);
echo html_writer::empty_tag('input',
    ['type' => 'hidden', 'name' => 'sesskey', 'value' => sesskey()]);

// Per-question scores (quiz mode).
if ($assign->assignmode === 'quiz') {
    $qanswers   = $DB->get_records('airagassign_answers',
        ['submissionid' => $submission->id]);
    $qquestions = $DB->get_records('airagassign_questions',
        ['assignid' => $assign->id], 'sortorder ASC');
    $qanswermap = [];
    foreach ($qanswers as $qa) {
        $qanswermap[$qa->questionid] = $qa;
    }
    $numq      = count($qquestions);
    $gradeperq = $numq > 0 ? (float)$assign->maximumgrade / $numq : 0;
    $gradeperq_inp = sprintf('%.2f', $gradeperq); // locale-safe for input attrs

    echo html_writer::tag('h6', get_string('perquestion_scores', 'airagassign'),
        ['class' => 'airag-section-title']);
    echo html_writer::start_tag('div', ['class' => 'airag-table-scroll']);
    echo html_writer::start_tag('table', ['class' => 'table table-sm table-bordered']);
    echo html_writer::tag('tr',
        html_writer::tag('th', '#') .
        html_writer::tag('th',
            get_string('score', 'airagassign') . ' / ' . format_float($gradeperq, 2)) .
        html_writer::tag('th', get_string('feedback', 'airagassign'))
    );
    $qnum = 1;
    foreach ($qquestions as $q) {
        $qa        = $qanswermap[$q->id] ?? null;
        $currscore = ($qa && $qa->score !== null)
            ? sprintf('%.2f', (float)$qa->score) : ''; // locale-safe
        $currfb    = $qa ? s($qa->feedback ?? '') : '';
        echo html_writer::tag('tr',
            html_writer::tag('td',
                html_writer::tag('strong', 'Q' . $qnum)) .
            html_writer::tag('td',
                html_writer::empty_tag('input', [
                    'type'     => 'number',
                    'class'    => 'form-control form-control-sm airag-qscore',
                    'name'     => 'answer_score_' . ($qa ? $qa->id : 0),
                    'value'    => $currscore, 'min' => '0',
                    'max'      => $gradeperq_inp, 'step' => '0.01',
                    'data-max' => $gradeperq_inp,
                ]) .
                html_writer::tag('div', '', ['class' => 'invalid-feedback'])) .
            html_writer::tag('td',
                html_writer::empty_tag('input', [
                    'type'        => 'text',
                    'class'       => 'form-control form-control-sm',
                    'name'        => 'answer_fb_' . ($qa ? $qa->id : 0),
                    'value'       => $currfb,
                    'placeholder' => get_string('feedback', 'airagassign'),
                ]))
        );
        $qnum++;
    }
    echo html_writer::end_tag('table');
    echo html_writer::end_tag('div');
}

// Overall / final grade.
$currgrade = ($submission->grade !== null)
    ? sprintf('%.2f', (float)$submission->grade) : ''; // locale-safe for input
$isquiz    = ($assign->assignmode === 'quiz');

echo html_writer::tag('label',
    get_string('finalgrade', 'airagassign') . ' (0 – ' . $maxgradeformatted . '):' .
    ($isquiz
        ? html_writer::tag('span',
            ' ' . get_string('autocalculated', 'airagassign'),
            ['class' => 'badge airag-badge-muted ms-2 fw-normal'])
        : ''),
    ['class' => 'form-label fw-bold', 'for' => 'id_finalgrade']);
echo html_writer::start_tag('div', ['class' => 'mb-3 position-relative']);

$gradeattrs = [
    'type'  => 'number', 'id' => 'id_finalgrade', 'name' => 'finalgrade',
    'min'   => '0', 'max' => $maxgrade_inp, 'step' => '0.01',
    'value' => $currgrade, 'required' => 'required',
];
if ($isquiz) {
    // Read-only: value is always the sum of per-question scores.
    // readonly inputs ARE still submitted with the form.
    $gradeattrs['class']    = 'form-control form-control-lg airag-grade-computed';
    $gradeattrs['readonly'] = 'readonly';
    $gradeattrs['tabindex'] = '-1';
    $gradeattrs['title']    = get_string('autocalculated_hint', 'airagassign');
} else {
    $gradeattrs['class']       = 'form-control form-control-lg';
    $gradeattrs['placeholder'] = '0 – ' . $maxgradeformatted;
}

echo html_writer::empty_tag('input', $gradeattrs);
echo html_writer::tag('div', '', ['class' => 'invalid-feedback fw-semibold']);
echo html_writer::end_tag('div'); // mb-3 wrapper

// Overall feedback.
$currfeedback = $submission->feedback ?? '';
echo html_writer::tag('label',
    get_string('overallfeedback', 'airagassign') . ':',
    ['class' => 'form-label', 'for' => 'id_finalfeedback']);
echo html_writer::tag('textarea', s($currfeedback), [
    'class' => 'form-control mb-3', 'id' => 'id_finalfeedback',
    'name'  => 'finalfeedback', 'rows' => 6,
]);

// Teacher note (internal).
echo html_writer::tag('label',
    '' . get_string('teacher_note', 'airagassign') . ' ' .
    html_writer::tag('small',
        '(' . get_string('teacher_note_internal', 'airagassign') . ')',
        ['class' => 'text-muted']),
    ['class' => 'form-label', 'for' => 'id_teachernote']);
echo html_writer::tag('textarea', s($submission->teacher_note ?? ''), [
    'class'       => 'form-control form-control-sm mb-4',
    'id'          => 'id_teachernote', 'name' => 'teacher_note', 'rows' => 2,
    'placeholder' => get_string('teacher_note_placeholder', 'airagassign'),
]);

// Submit row.
echo html_writer::start_tag('div', ['class' => 'airag-action-row']);
echo html_writer::tag('button',
    '' . get_string('savefinalgrade', 'airagassign'),
    ['type' => 'submit', 'class' => 'btn btn-airag-primary btn-lg']);
echo html_writer::link($returnurl, get_string('cancel', 'core'),
    ['class' => 'btn btn-airag-outline-secondary btn-lg']);
echo html_writer::end_tag('div');

echo html_writer::end_tag('form');
echo html_writer::end_tag('section'); // Grading form column.
echo html_writer::end_tag('div'); // Two-column layout.
echo html_writer::end_tag('div'); // airagassign-workflow-page.

echo <<<JSBLOCK
<script>
(function () {
    'use strict';

    /* ── DOM refs ──────────────────────────────────────────────────────────── */
    var form      = document.querySelector('form[method="post"]');
    var totalInp  = document.getElementById('id_finalgrade');
    var MAX       = totalInp ? (parseFloat(totalInp.getAttribute('max')) || 0) : 0;
    var submitBtn = form ? form.querySelector('button[type="submit"]') : null;
    var qscores   = document.querySelectorAll('.airag-qscore');
    var isQuiz    = qscores.length > 0;

    /* ── feedback helper ───────────────────────────────────────────────────── */
    function setValidity(input, ok, msg) {
        input.classList.toggle('is-invalid', !ok);
        input.classList.toggle('is-valid',   ok && input.value !== '');
        var fb = input.parentNode.querySelector('.invalid-feedback');
        if (fb) fb.textContent = ok ? '' : msg;
    }

    /* ── validate one number input against its max attr ───────────────────── */
    function validateInput(input) {
        if (!input || input.readOnly) return true; // skip read-only computed fields
        var maxAttr = input.getAttribute('max');
        var max     = maxAttr !== null ? parseFloat(maxAttr) : NaN;
        var val     = parseFloat(input.value);
        if (input.value.trim() === '' || isNaN(val)) {
            setValidity(input, false, 'Nilai harus diisi dengan angka.');
            return false;
        }
        if (val < 0) {
            setValidity(input, false, 'Nilai tidak boleh kurang dari 0.');
            return false;
        }
        if (!isNaN(max) && val > max) {
            setValidity(input, false,
                'Nilai melebihi batas maksimum (' + max + ').');
            return false;
        }
        setValidity(input, true, '');
        return true;
    }

    /* ── quiz: auto-sum per-question scores → fill computed total ──────────── */
    function syncTotal() {
        if (!isQuiz || !totalInp) return;
        var sum = 0;
        qscores.forEach(function (inp) {
            var v = parseFloat(inp.value);
            if (!isNaN(v) && v >= 0) sum += v;
        });
        sum = Math.round(sum * 100) / 100;
        totalInp.value = sum > MAX ? MAX : sum;
        // visual feedback on the computed field: highlight if at max
        totalInp.classList.toggle('airag-grade-computed-full', totalInp.value == MAX && MAX > 0);
    }

    /* ── check all editable number inputs and enable/disable submit ─────────── */
    function updateSubmitState() {
        if (!form) return;
        var allOk = true;
        form.querySelectorAll('input[type="number"]:not([readonly])').forEach(function (inp) {
            if (!validateInput(inp)) allOk = false;
        });
        // also ensure total has a value in quiz mode
        if (isQuiz && totalInp && totalInp.value.trim() === '') allOk = false;
        if (submitBtn) submitBtn.disabled = !allOk;
    }

    /* ── wire per-question score inputs ───────────────────────────────────── */
    qscores.forEach(function (inp) {
        ['input', 'blur'].forEach(function (ev) {
            inp.addEventListener(ev, function () {
                validateInput(inp);
                syncTotal();
                updateSubmitState();
            });
        });
    });

    /* ── wire total/final grade input (essay mode only — not read-only) ───── */
    if (totalInp && !totalInp.readOnly) {
        ['input', 'blur'].forEach(function (ev) {
            totalInp.addEventListener(ev, function () {
                validateInput(totalInp);
                updateSubmitState();
            });
        });
    }

    /* ── run sync once on page load to populate total from existing scores ── */
    if (isQuiz) {
        syncTotal();
        updateSubmitState();
    }

    /* ── block submit when any editable field is invalid ───────────────────── */
    if (form) {
        form.addEventListener('submit', function (e) {
            var allOk = true;
            form.querySelectorAll('input[type="number"]:not([readonly])').forEach(function (inp) {
                if (!validateInput(inp)) allOk = false;
            });
            if (!allOk) {
                e.preventDefault();
                var first = form.querySelector('.is-invalid');
                if (first) first.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        });
    }
})();
</script>
JSBLOCK;

echo $OUTPUT->footer();
