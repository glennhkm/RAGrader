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
 * Human-in-the-loop: Teacher reviews AI suggestion and accepts or overrides.
 *
 * The AI grading pipeline stores its result in ai_grade / ai_feedback columns
 * (status = 'ai_suggested').  This page lets the teacher decide:
 *   Accept   → copies ai_grade → grade, ai_score → score; status = 'graded', graded_by = 'ai_confirmed'
 *   Override → teacher fills in custom grade/feedback;   status = 'graded', graded_by = 'teacher'
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
require_once(__DIR__ . '/lib.php');

$id           = required_param('id', PARAM_INT);           // Course module ID.
$submissionid = required_param('submissionid', PARAM_INT); // Submission ID.

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

$PAGE->set_url('/mod/airagassign/grade_review.php',
    ['id' => $cm->id, 'submissionid' => $submissionid]);
$PAGE->set_title(get_string('reviewaisuggestion', 'airagassign') . ': ' . fullname($user));
$PAGE->set_heading(format_string($course->fullname));

// ============================================================
// POST HANDLER — teacher accepts or overrides the AI suggestion
// ============================================================
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    require_sesskey();

    $gradeaction = required_param('gradeaction', PARAM_ALPHA); // 'accept' or 'override'

    if ($gradeaction === 'accept') {
        // ── Accept: promote AI suggestion to the final grade ───────────────────
        $submission->grade      = $submission->ai_grade;
        $submission->feedback   = $submission->ai_feedback;
        $submission->status     = 'graded';
        $submission->graded_by  = 'ai_confirmed';
        $submission->timegraded = time();
        $DB->update_record('airagassign_submissions', $submission);

        // Copy ai_score → score and ai_feedback → feedback for every answer row.
        $ansrecs = $DB->get_records('airagassign_answers', ['submissionid' => $submission->id]);
        foreach ($ansrecs as $ar) {
            if ($ar->ai_score !== null) {
                $ar->score    = $ar->ai_score;
                $ar->feedback = $ar->ai_feedback ?? '';
                $DB->update_record('airagassign_answers', $ar);
            }
        }

        airagassign_update_grades($assign, $submission->userid, false);

        redirect(
            new moodle_url('/mod/airagassign/view_result.php',
                ['id' => $cm->id, 'submissionid' => $submission->id]),
            get_string('gradeaccepted', 'airagassign'),
            null,
            \core\output\notification::NOTIFY_SUCCESS
        );

    } else {
        // ── Override: teacher sets their own final grade ───────────────────────
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

        // Update per-question scores if provided (quiz mode).
        if ($assign->assignmode === 'quiz') {
            $ansrecs   = $DB->get_records('airagassign_answers', ['submissionid' => $submission->id]);
            $questions = $DB->get_records('airagassign_questions', ['assignid' => $assign->id], 'sortorder ASC');
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
            // Essay: mirror the submission grade to the single answer row.
            $ar = $DB->get_record('airagassign_answers', ['submissionid' => $submission->id]);
            if ($ar) {
                $ar->score    = $finalgrade;
                $ar->feedback = $finalfeedback;
                $DB->update_record('airagassign_answers', $ar);
            }
        }

        airagassign_update_grades($assign, $submission->userid, false);

        redirect($returnurl, get_string('gradeoverridden', 'airagassign'),
            null, \core\output\notification::NOTIFY_SUCCESS);
    }
}

// ============================================================
// GET — display the review page
// ============================================================

// Build filename → ['title', 'url'] map for citation rendering.
$filemaprows = $DB->get_records_sql(
    "SELECT af.filename, am.name AS materialtitle, am.id AS materialid
       FROM {airagmaterial_files} af
       JOIN {airagmaterial} am ON am.id = af.materialid
       JOIN {airagassign_materials} aam ON aam.materialid = am.id
      WHERE aam.assignid = ?",
    [$assign->id]
);
$filemap = [];
foreach ($filemaprows as $row) {
    $entry = [
        'title' => $row->materialtitle,
        'url'   => new moodle_url('/mod/airagmaterial/view.php', ['m' => $row->materialid]),
    ];
    $filemap[$row->filename] = $entry;
    $base = basename($row->filename);
    if ($base !== $row->filename) {
        $filemap[$base] = $entry;
    }
}

$PAGE->requires->css('/mod/airagassign/styles.css');
echo $OUTPUT->header();
echo html_writer::start_tag('div', ['class' => 'airagassign-workflow-page']);
echo $OUTPUT->heading(get_string('reviewaisuggestion', 'airagassign') . ': ' . fullname($user));

// Navigation.
echo html_writer::start_tag('nav', ['class' => 'airag-navigation', 'aria-label' => get_string('actions')]);
echo html_writer::link($returnurl,
    '&larr; ' . get_string('backtoassignment', 'airagassign'),
    ['class' => 'btn btn-airag-outline-secondary airag-back-btn']);
echo html_writer::link(
    new moodle_url('/mod/airagassign/grade_manual.php',
        ['id' => $cm->id, 'submissionid' => $submission->id]),
    get_string('grademanually', 'airagassign'),
    ['class' => 'btn btn-airag-outline-primary']
);
echo html_writer::end_tag('nav');

// HITL info banner.
echo html_writer::tag('div',
    get_string('hitl_info', 'airagassign'),
    ['class' => 'airag-banner airag-banner-info']
);

// ── Two-column layout ─────────────────────────────────────────────────────────
echo html_writer::start_tag('div', ['class' => 'airag-two-column']);

// ── LEFT: Student submission ──────────────────────────────────────────────────
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
        echo html_writer::start_tag('div', ['class' => 'card mb-2 airag-accent-card']);
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
        ['style' => 'max-height:500px;overflow-y:auto;font-size:.9rem']);
    echo html_writer::end_tag('div');
    echo html_writer::end_tag('div');
}

echo html_writer::end_tag('section'); // Student submission column.

// ── RIGHT: AI suggestion ──────────────────────────────────────────────────────
echo html_writer::start_tag('section', ['class' => 'airag-column']);
echo html_writer::tag('h6', get_string('aisuggestion', 'airagassign'),
    ['class' => 'airag-section-title']);

$aipct       = ($assign->maximumgrade > 0 && $submission->ai_grade !== null)
    ? round(($submission->ai_grade / $assign->maximumgrade) * 100, 1) : 0;
$aibordercls = $aipct >= 70 ? 'border-airag-success' : ($aipct >= 50 ? 'border-airag-primary' : 'border-airag-error');
$aiheadercls = $aipct >= 70 ? 'airag-card-header-success' : ($aipct >= 50 ? 'airag-card-header-primary' : 'airag-card-header-error');
// $aiscorecls  = $aipct >= 70 ? 'airag-score-pass' : ($aipct >= 50 ? 'airag-score-mid' : 'airag-score-fail');

echo html_writer::start_tag('div', ['class' => 'card ' . $aibordercls . ' mb-3']);
echo html_writer::tag('div',
    html_writer::tag('h5',
        get_string('aisuggested_grade', 'airagassign') . ': ' .
        html_writer::tag('span',
            format_float($submission->ai_grade ?? 0, 2) . ' / ' .
            format_float($assign->maximumgrade, 2),
            ['class' => 'text-neutral']
        ) .
        html_writer::tag('span', " ($aipct%)", ['class' => 'ms-1 opacity-75 small']),
        ['class' => 'mb-0']
    ),
    ['class' => 'card-header ' . $aiheadercls . ' py-2']);

echo html_writer::start_tag('div', ['class' => 'card-body']);

if (airagassign_has_confidence($submission)) {
    $confpct = round($submission->confidence * 100, 1);
    echo html_writer::tag('p',
        get_string('confidence', 'airagassign') . ': ' .
        html_writer::tag('span', "$confpct%", ['class' => 'badge airag-badge-info']),
        ['class' => 'mb-2']
    );
}

if (!empty($submission->ai_feedback)) {
    echo html_writer::tag('h6', get_string('overallfeedback', 'airagassign') . ':');
    echo html_writer::tag('div', nl2br(s($submission->ai_feedback)),
        ['class' => 'airag-feedback-block mb-3 small']);
}

// Criterion scores + citations from ai_response JSON.
$aidata = !empty($submission->ai_response) ? json_decode($submission->ai_response, true) : null;

if ($aidata) {
    // Criterion scores.
    $criterionscores = $aidata['criterion_scores'] ?? [];
    $showcriterionscores = (($assign->rubricmode ?? '') === 'custom');
    if ($showcriterionscores && !empty($criterionscores)) {
        echo html_writer::start_tag('details', ['open' => '']);
        echo html_writer::tag('summary',
            get_string('criteriascores', 'airagassign'),
            ['class' => 'btn btn-sm btn-airag-outline-info mb-2']);
        echo html_writer::start_tag('div', ['class' => 'airag-table-scroll']);
        echo html_writer::start_tag('table',
            ['class' => 'table table-sm table-bordered small']);
        echo html_writer::tag('tr',
            html_writer::tag('th', get_string('criterionname', 'airagassign')) .
            html_writer::tag('th', get_string('score', 'airagassign')) .
            html_writer::tag('th', get_string('feedback', 'airagassign'))
        );
        foreach ($criterionscores as $cname => $cdata) {
            $cscore = is_array($cdata) ? ($cdata['score'] ?? '-') : $cdata;
            $cfb    = is_array($cdata) ? ($cdata['feedback'] ?? '') : '';
            echo html_writer::tag('tr',
                html_writer::tag('td', s($cname)) .
                html_writer::tag('td',
                    is_numeric($cscore) ? format_float($cscore, 2) : s($cscore)) .
                html_writer::tag('td', s($cfb))
            );
        }
        echo html_writer::end_tag('table');
        echo html_writer::end_tag('div');
        echo html_writer::end_tag('details');
    }

    // Citations.
    $citations = $aidata['citations'] ?? [];
    if (!empty($citations)) {
        echo html_writer::start_tag('details');
        echo html_writer::tag('summary',
            get_string('citations', 'airagassign'),
            ['class' => 'btn btn-sm btn-airag-outline-secondary mb-2']);
        echo html_writer::start_tag('ul', ['class' => 'list-group list-group-flush small']);
        foreach ($citations as $cit) {
            $cittext   = is_array($cit) ? ($cit['text']   ?? '') : (string)$cit;
            $citsource = is_array($cit) ? ($cit['source'] ?? '') : '';
            $citpage   = is_array($cit) ? ($cit['page']   ?? null) : null;
            $srcbase   = basename($citsource);
            $matinfo   = $filemap[$citsource] ?? $filemap[$srcbase] ?? null;
            $mattitle  = $matinfo ? $matinfo['title'] : ($srcbase ?: $citsource);
            $maturl    = $matinfo ? $matinfo['url']   : null;

            // Derive file-type icon from the source filename (same approach as view.php).
            // mimeinfo('icon', filename) returns the Moodle pix icon name for the extension.
            $iconname = mimeinfo('icon', $srcbase ?: 'file.bin');
            $fileicon = $OUTPUT->pix_icon(
                'f/' . $iconname,
                $iconname,          // alt text = icon name (e.g. "pdf", "powerpoint")
                'moodle',
                ['class' => 'iconsmall me-1']
            );

            // Page badge.
            $pagebadge = ($citpage !== null && $citpage !== ''
                && strtolower((string)$citpage) !== 'n/a')
                ? ' ' . html_writer::tag('span',
                    get_string('page', 'airagassign') . ' ' . s((string)$citpage),
                    ['class' => 'badge airag-badge-muted'])
                : '';

            // Source: icon + linked material name (or plain text if no URL found).
            $srclabel = $fileicon . s($mattitle);
            $srclink  = $maturl
                ? html_writer::link($maturl, $srclabel,
                    ['target' => '_blank', 'title' => s($citsource),
                     'class'  => 'text-decoration-none'])
                : html_writer::tag('span', $srclabel);

            echo html_writer::tag('li',
                html_writer::tag('em', '"' . s($cittext) . '"',
                    ['class' => 'd-block small']) .
                html_writer::tag('span',
                    $srclink . $pagebadge,
                    ['class' => 'airag-citation-source']),
                ['class' => 'list-group-item px-0']
            );
        }
        echo html_writer::end_tag('ul');
        echo html_writer::end_tag('details');
    }
}

echo html_writer::end_tag('div'); // card-body
echo html_writer::end_tag('div'); // ai card
echo html_writer::end_tag('section'); // AI suggestion column.
echo html_writer::end_tag('div'); // Two-column layout.

// ============================================================
// DECISION FORM
// ============================================================
echo html_writer::tag('hr', '');
echo html_writer::tag('h5', get_string('grading_decision', 'airagassign'),
    ['class' => 'airag-section-title mt-3']);

$formurl           = new moodle_url('/mod/airagassign/grade_review.php',
    ['id' => $cm->id, 'submissionid' => $submission->id]);
// format_float() respects user locale (e.g. "10,00" in ID) — fine for display text.
// For HTML number input value/min/max attributes we MUST use "." as decimal separator.
$aigradeformatted  = format_float($submission->ai_grade ?? 0, 2); // display only
$maxgradeformatted = format_float($assign->maximumgrade, 2);       // display only
$aigrade_inp       = sprintf('%.2f', (float)($submission->ai_grade ?? 0)); // input attr
$maxgrade_inp      = sprintf('%.2f', (float)$assign->maximumgrade);         // input attr
$isquiz            = ($assign->assignmode === 'quiz');

echo html_writer::start_tag('form',
    ['method' => 'post', 'action' => $formurl, 'id' => 'airag-review-form']);
echo html_writer::empty_tag('input',
    ['type' => 'hidden', 'name' => 'sesskey', 'value' => sesskey()]);

// Accept / Override radio buttons.
echo html_writer::start_tag('div', ['class' => 'airag-decision-group mb-4', 'role' => 'radiogroup']);

echo html_writer::tag('input', '',
    ['type' => 'radio', 'class' => 'airag-decision-input',
     'name' => 'gradeaction', 'id' => 'opt_accept',
     'value' => 'accept', 'checked' => 'checked']);
echo html_writer::tag('label',
    '' . get_string('accept_ai_suggestion', 'airagassign') .
    html_writer::tag('span', " ($aigradeformatted / $maxgradeformatted)",
        ['class' => 'ms-1 opacity-75']),
    ['class' => 'btn btn-airag-outline-success flex-fill py-3', 'for' => 'opt_accept']);

echo html_writer::tag('input', '',
    ['type' => 'radio', 'class' => 'airag-decision-input',
     'name' => 'gradeaction', 'id' => 'opt_override', 'value' => 'override']);
echo html_writer::tag('label',
    '' . get_string('override_grade', 'airagassign'),
    ['class' => 'btn btn-airag-outline-primary flex-fill py-3', 'for' => 'opt_override']);

echo html_writer::end_tag('div'); // btn-group

// Override panel (hidden by default).
echo html_writer::start_tag('div',
    ['id' => 'airag-override-panel',
     'class' => 'card border-airag-primary mb-4', 'style' => 'display:none']);
echo html_writer::tag('div',
    get_string('override_grade', 'airagassign'),
    ['class' => 'card-header airag-card-header-primary fw-semibold py-2']);
echo html_writer::start_tag('div', ['class' => 'card-body']);

// Final grade input.
echo html_writer::start_tag('div', ['class' => 'row mb-3']);
echo html_writer::start_tag('div', ['class' => 'col-md-5']);
echo html_writer::tag('label',
    get_string('finalgrade', 'airagassign') . ' (0 – ' . $maxgradeformatted . '):' .
    ($isquiz
        ? html_writer::tag('span',
            ' ' . get_string('autocalculated', 'airagassign'),
            ['class' => 'badge airag-badge-muted ms-2 fw-normal'])
        : ''),
    ['class' => 'form-label fw-bold', 'for' => 'id_finalgrade']);

$gradeattrs = [
    'type'  => 'number', 'id' => 'id_finalgrade', 'name' => 'finalgrade',
    'min'   => '0', 'max' => $maxgrade_inp, 'step' => '0.01',
    'value' => $aigrade_inp,
];
if ($isquiz) {
    $gradeattrs['class']    = 'form-control form-control-lg airag-grade-computed';
    $gradeattrs['readonly'] = 'readonly';
    $gradeattrs['tabindex'] = '-1';
    $gradeattrs['title']    = get_string('autocalculated_hint', 'airagassign');
} else {
    $gradeattrs['class'] = 'form-control form-control-lg';
}
echo html_writer::empty_tag('input', $gradeattrs);
echo html_writer::tag('div', '', ['class' => 'invalid-feedback fw-semibold']);
echo html_writer::end_tag('div'); // col-md-5
echo html_writer::end_tag('div'); // row.mb-3

// Per-question override (quiz mode only).
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
        ['class' => 'airag-section-title mt-2']);
    echo html_writer::start_tag('div', ['class' => 'airag-table-scroll']);
    echo html_writer::start_tag('table', ['class' => 'table table-sm table-bordered']);
    echo html_writer::tag('tr',
        html_writer::tag('th', '#') .
        html_writer::tag('th', get_string('youranswer', 'airagassign')) .
        html_writer::tag('th',
            get_string('score', 'airagassign') .
            ' (/ ' . format_float($gradeperq, 2) . ')') .
        html_writer::tag('th', get_string('feedback', 'airagassign'))
    );
    $qnum = 1;
    foreach ($qquestions as $q) {
        $qa          = $qanswermap[$q->id] ?? null;
        $aiscore_inp = sprintf('%.2f', (float)($qa->ai_score ?? 0)); // locale-safe
        $aifb        = $qa ? s($qa->ai_feedback ?? '') : '';
        echo html_writer::tag('tr',
            html_writer::tag('td', $qnum) .
            html_writer::tag('td',
                html_writer::tag('small',
                    s($qa ? mb_substr($qa->answertext, 0, 80) . '…' : '-'))) .
            html_writer::tag('td',
                html_writer::empty_tag('input', [
                    'type'     => 'number',
                    'class'    => 'form-control form-control-sm airag-qscore',
                    'name'     => 'answer_score_' . ($qa ? $qa->id : 0),
                    'value'    => $aiscore_inp, 'min' => '0',
                    'max'      => $gradeperq_inp, 'step' => '0.01',
                    'data-max' => $gradeperq_inp,
                ]) .
                html_writer::tag('div', '', ['class' => 'invalid-feedback'])) .
            html_writer::tag('td',
                html_writer::empty_tag('input', [
                    'type'        => 'text',
                    'class'       => 'form-control form-control-sm',
                    'name'        => 'answer_fb_' . ($qa ? $qa->id : 0),
                    'value'       => $aifb,
                    'placeholder' => get_string('feedback', 'airagassign'),
                ]))
        );
        $qnum++;
    }
    echo html_writer::end_tag('table');
    echo html_writer::end_tag('div');
}

// Overall feedback (pre-filled with AI feedback so teacher can edit it).
echo html_writer::tag('label',
    get_string('overallfeedback', 'airagassign') . ':',
    ['class' => 'form-label', 'for' => 'id_override_feedback']);
echo html_writer::tag('textarea', s($submission->ai_feedback ?? ''), [
    'class' => 'form-control mb-3', 'id' => 'id_override_feedback',
    'name'  => 'finalfeedback', 'rows' => 5,
]);

// Teacher note (internal — not shown to students).
echo html_writer::tag('label',
    '' . get_string('teacher_note', 'airagassign') . ' ' .
    html_writer::tag('small',
        '(' . get_string('teacher_note_internal', 'airagassign') . ')',
        ['class' => 'text-muted']),
    ['class' => 'form-label', 'for' => 'id_teachernote']);
echo html_writer::tag('textarea', '', [
    'class'       => 'form-control form-control-sm mb-2',
    'id'          => 'id_teachernote', 'name' => 'teacher_note', 'rows' => 2,
    'placeholder' => get_string('teacher_note_placeholder', 'airagassign'),
]);

echo html_writer::end_tag('div'); // card-body
echo html_writer::end_tag('div'); // override panel card

// Submit row.
echo html_writer::start_tag('div', ['class' => 'airag-action-row']);
echo html_writer::tag('button',
    '' . get_string('confirmgrade', 'airagassign'),
    ['type' => 'submit', 'class' => 'btn btn-airag-primary btn-lg',
     'id' => 'airag-confirm-btn']);
echo html_writer::link($returnurl, get_string('cancel', 'core'),
    ['class' => 'btn btn-airag-outline-secondary btn-lg']);
echo html_writer::end_tag('div');

echo html_writer::end_tag('form');
echo html_writer::end_tag('div'); // airagassign-workflow-page.

// JS: real-time validation + toggle override panel.
echo <<<JSBLOCK
<script>
(function () {
    'use strict';

    /* ── DOM refs ──────────────────────────────────────────────────────────── */
    var form      = document.getElementById('airag-review-form');
    var submitBtn = document.getElementById('airag-confirm-btn');
    var totalInp  = document.getElementById('id_finalgrade');
    var MAX       = totalInp ? (parseFloat(totalInp.getAttribute('max')) || 0) : 0;
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
        if (!input || input.readOnly) return true; // skip computed read-only fields
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
        totalInp.classList.toggle('airag-grade-computed-full',
            parseFloat(totalInp.value) === MAX && MAX > 0);
    }

    /* ── check all override inputs and enable/disable submit ──────────────── */
    function updateSubmitState() {
        var action = document.querySelector('input[name="gradeaction"]:checked');
        if (!action || action.value !== 'override') {
            if (submitBtn) submitBtn.disabled = false;
            return;
        }
        var allOk = true;
        document.querySelectorAll('#airag-override-panel input[type="number"]:not([readonly])')
            .forEach(function (inp) {
                if (!validateInput(inp)) allOk = false;
            });
        // in quiz mode the computed total must have a value
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

    /* ── wire total/final grade input (essay mode only) ─────────────────────── */
    if (totalInp && !totalInp.readOnly) {
        ['input', 'blur'].forEach(function (ev) {
            totalInp.addEventListener(ev, function () {
                validateInput(totalInp);
                updateSubmitState();
            });
        });
    }

    /* ── toggle override panel ─────────────────────────────────────────────── */
    function toggle() {
        var sel   = document.querySelector('input[name="gradeaction"]:checked');
        var panel = document.getElementById('airag-override-panel');
        if (!sel || !panel || !submitBtn) return;
        var isOverride = sel.value === 'override';
        panel.style.display = isOverride ? '' : 'none';
        submitBtn.innerHTML = isOverride
            ? 'Simpan Nilai Akhir'
            : 'Konfirmasi Nilai AI';
        // Clear validation state when switching away from override.
        if (!isOverride) {
            document.querySelectorAll('#airag-override-panel .is-invalid, #airag-override-panel .is-valid')
                .forEach(function (el) {
                    el.classList.remove('is-invalid', 'is-valid');
                    var fb = el.parentNode && el.parentNode.querySelector('.invalid-feedback');
                    if (fb) fb.textContent = '';
                });
        }
        // When override panel opens, sync computed total (quiz) and update submit state.
        if (isOverride && isQuiz) syncTotal();
        updateSubmitState();
    }

    document.querySelectorAll('input[name="gradeaction"]')
        .forEach(function (r) { r.addEventListener('change', toggle); });

    /* ── block submit when override panel has errors ──────────────────────── */
    if (form) {
        form.addEventListener('submit', function (e) {
            var action = document.querySelector('input[name="gradeaction"]:checked');
            if (action && action.value === 'override') {
                var allOk = true;
                document.querySelectorAll('#airag-override-panel input[type="number"]:not([readonly])')
                    .forEach(function (inp) {
                        if (!validateInput(inp)) allOk = false;
                    });
                if (!allOk) {
                    e.preventDefault();
                    var first = document.querySelector('#airag-override-panel .is-invalid');
                    if (first) first.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
            }
        });
    }

    /* ── init ──────────────────────────────────────────────────────────────── */
    toggle();
})();
</script>
JSBLOCK;

echo $OUTPUT->footer();
