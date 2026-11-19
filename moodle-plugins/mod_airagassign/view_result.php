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
 * View detailed AI grading results for a submission.
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

$id = required_param('id', PARAM_INT);
$submissionid = required_param('submissionid', PARAM_INT);

$cm = get_coursemodule_from_id('airagassign', $id, 0, false, MUST_EXIST);
$course = get_course($cm->course);
$assign = $DB->get_record('airagassign', ['id' => $cm->instance], '*', MUST_EXIST);

require_login($course, true, $cm);
$context = context_module::instance($cm->id);
require_capability('mod/airagassign:view', $context);

$submission = $DB->get_record('airagassign_submissions', ['id' => $submissionid, 'assignid' => $assign->id], '*', MUST_EXIST);

// Build a map: filename (as stored by Python) → ['title' => material name, 'url' => view URL].
// This lets citation sources be shown as the human-readable material title with a link.
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
    $filemap[$row->filename] = [
        'title' => $row->materialtitle,
        'url'   => new moodle_url('/mod/airagmaterial/view.php', ['m' => $row->materialid]),
    ];
    // Also index by basename in case Python stored the full path.
    $base = basename($row->filename);
    if ($base !== $row->filename) {
        $filemap[$base] = $filemap[$row->filename];
    }
}

// Ensure student can only view their own result.
$cangrade = has_capability('mod/airagassign:grade', $context);
if (!$cangrade && $submission->userid != $USER->id) {
    throw new moodle_exception('nopermission');
}

$user = $DB->get_record('user', ['id' => $submission->userid]);

$PAGE->set_url('/mod/airagassign/view_result.php', ['id' => $cm->id, 'submissionid' => $submissionid]);
$PAGE->set_title(get_string('resultsfor', 'airagassign', fullname($user)));
$PAGE->set_heading(format_string($course->fullname));

$PAGE->requires->css('/mod/airagassign/styles.css');
echo $OUTPUT->header();
echo html_writer::start_tag('div', ['class' => 'airagassign-result-page']);
echo $OUTPUT->heading(get_string('resultsfor', 'airagassign', fullname($user)));

// Back button.
$backurl = new moodle_url('/mod/airagassign/view.php', ['id' => $cm->id]);
echo html_writer::link($backurl,
    '&larr; ' . get_string('backtoassignment', 'airagassign'),
    ['class' => 'btn btn-airag-outline-secondary mb-3 airag-back-btn']);

// Overall score.
echo html_writer::start_tag('div', ['class' => 'card mb-3']);
echo html_writer::start_tag('div', ['class' => 'card-body']);
echo html_writer::tag('h4', get_string('overallscore', 'airagassign'), ['class' => 'card-title']);

$scorepercentage = ($assign->maximumgrade > 0)
    ? round(($submission->grade / $assign->maximumgrade) * 100, 1)
    : 0;
$scoreclass = 'airag-score-pass';
if ($scorepercentage < 50) {
    $scoreclass = 'airag-score-fail';
} else if ($scorepercentage < 70) {
    $scoreclass = 'airag-score-mid';
}

echo html_writer::tag('h2',
    html_writer::tag('span', format_float($submission->grade, 2), ['class' => $scoreclass]) .
    ' / ' . format_float($assign->maximumgrade, 2) .
    html_writer::tag('small', " ($scorepercentage%)", ['class' => 'text-muted ms-1']),
    ['class' => 'mb-2']
);

if (airagassign_has_confidence($submission)) {
    $confpct = round($submission->confidence * 100, 1);
    echo html_writer::tag('p', get_string('confidence', 'airagassign') . ': ' .
        html_writer::tag('span', "$confpct%", ['class' => 'badge airag-badge-info']),
        ['class' => 'mb-1']
    );
}

echo html_writer::tag('p',
    get_string('gradedat', 'airagassign') . ': ' . userdate($submission->timegraded),
    ['class' => 'text-muted small']
);

// ── Who confirmed this grade? ────────────────────────────────────────────────
$gradedby = $submission->graded_by ?? null;
if ($gradedby === 'ai_confirmed') {
    echo html_writer::tag('p',
        get_string('gradedby_ai_confirmed', 'airagassign'),
        ['class' => 'text-airag-success small mb-1']);
} else if ($gradedby === 'teacher') {
    echo html_writer::tag('p',
        get_string('gradedby_teacher', 'airagassign'),
        ['class' => 'text-airag-info small mb-1']);
    if (!empty($submission->teacher_note)) {
        echo html_writer::tag('p',
            html_writer::tag('em', s($submission->teacher_note)),
            ['class' => 'small text-muted mb-1']);
    }
} else {
    // Legacy submissions (before HITL) were AI-graded without teacher review.
    echo html_writer::tag('p',
        get_string('gradedby', 'airagassign'),
        ['class' => 'text-muted small mb-1']);
}

// ── If teacher overrode AI, show original AI suggestion in a collapsible ─────
if ($gradedby === 'teacher'
        && isset($submission->ai_grade) && $submission->ai_grade !== null) {
    echo html_writer::start_tag('details', ['class' => 'mt-2 mb-1']);
    echo html_writer::tag('summary',
        '' . get_string('ai_original_suggestion', 'airagassign'),
        ['class' => 'btn btn-sm btn-airag-outline-secondary mb-2']);
    echo html_writer::start_tag('div', ['class' => 'card card-body bg-light small']);
    echo html_writer::tag('p',
        get_string('aisuggested_grade', 'airagassign') . ': ' .
        html_writer::tag('strong',
            format_float($submission->ai_grade, 2) . ' / ' .
            format_float($assign->maximumgrade, 2)),
        ['class' => 'mb-1']);
    if (!empty($submission->ai_feedback)) {
        echo html_writer::tag('p', nl2br(s($submission->ai_feedback)),
            ['class' => 'mb-0 text-muted']);
    }
    echo html_writer::end_tag('div');
    echo html_writer::end_tag('details');
}
// ─────────────────────────────────────────────────────────────────────────────
echo html_writer::end_tag('div');
echo html_writer::end_tag('div');

// Overall feedback.
if (!empty($submission->feedback)) {
    echo html_writer::start_tag('div', ['class' => 'card mb-3']);
    echo html_writer::start_tag('div', ['class' => 'card-body']);
    echo html_writer::tag('h4', get_string('overallfeedback', 'airagassign'), ['class' => 'card-title']);
    echo html_writer::tag('div', nl2br(s($submission->feedback)), ['class' => 'card-text']);
    echo html_writer::end_tag('div');
    echo html_writer::end_tag('div');
}

// Per-question details (quiz mode) or single essay details.
$answers = $DB->get_records('airagassign_answers', ['submissionid' => $submission->id]);

if ($assign->assignmode === 'quiz') {
    $questions = $DB->get_records('airagassign_questions', ['assignid' => $assign->id], 'sortorder ASC');
    $answermap = [];
    foreach ($answers as $ans) {
        $answermap[$ans->questionid] = $ans;
    }

    echo html_writer::tag('h3', get_string('questionsheader', 'airagassign'), ['class' => 'mt-4']);

    $qnum = 1;
    foreach ($questions as $q) {
        $ans = $answermap[$q->id] ?? null;

        echo html_writer::start_tag('div', ['class' => 'card mb-3']);
        echo html_writer::start_tag('div', ['class' => 'card-header']);
        echo html_writer::tag('h5', get_string('questiontext', 'airagassign', $qnum) . ': ' . s($q->questiontext));
        echo html_writer::end_tag('div');
        echo html_writer::start_tag('div', ['class' => 'card-body']);

        if ($ans) {
            echo html_writer::tag('h6', get_string('answer', 'airagassign') . ':', ['class' => 'text-muted']);
            echo html_writer::tag('p', nl2br(s($ans->answertext)));

            if ($ans->score !== null) {
                $gradeperq = ($assign->maximumgrade > 0 && count($questions) > 0)
                    ? $assign->maximumgrade / count($questions) : 0;
                echo html_writer::tag('p',
                    html_writer::tag('strong', get_string('score', 'airagassign') . ': ') .
                    format_float($ans->score, 2) . ' / ' . format_float($gradeperq, 2)
                );
            }

            if (!empty($ans->feedback)) {
                echo html_writer::tag('p',
                    html_writer::tag('strong', get_string('feedback', 'airagassign') . ': ') .
                    s($ans->feedback)
                );
            }

            // Show detailed AI response data only when graded by AI (not teacher-overridden).
            // When teacher manually graded or overrode, per-criterion AI details are not shown;
            // the teacher-supplied per-question feedback above is the authoritative source.
            if ($gradedby !== 'teacher' && !empty($ans->ai_response)) {
                $aidata = json_decode($ans->ai_response, true);
                if ($aidata) {
                    airagassign_render_ai_details(
                        $aidata,
                        $OUTPUT,
                        $filemap,
                        ($assign->rubricmode ?? '') === 'custom'
                    );
                }
            }
        } else {
            echo html_writer::tag('p', '-', ['class' => 'text-muted']);
        }

        echo html_writer::end_tag('div');
        echo html_writer::end_tag('div');

        $qnum++;
    }
} else {
    // Essay mode: show single answer details.
    $answer = reset($answers);
    if ($answer) {
        echo html_writer::start_tag('div', ['class' => 'card mb-3']);
        echo html_writer::start_tag('div', ['class' => 'card-header']);
        echo html_writer::tag('h5', get_string('youressay', 'airagassign'));
        echo html_writer::end_tag('div');
        echo html_writer::start_tag('div', ['class' => 'card-body']);
        echo html_writer::tag('div', nl2br(s($answer->answertext)), ['style' => 'max-height:400px;overflow-y:auto;']);
        echo html_writer::end_tag('div');
        echo html_writer::end_tag('div');

        // Show detailed AI response only when graded by AI (not teacher-overridden).
        // When teacher manually graded or overrode, per-criterion AI details are not shown;
        // the overall feedback above is the authoritative source.
        if ($gradedby !== 'teacher') {
            $aidata = !empty($submission->ai_response) ? json_decode($submission->ai_response, true) : null;
            if (!$aidata && !empty($answer->ai_response)) {
                $aidata = json_decode($answer->ai_response, true);
            }
            if ($aidata) {
                airagassign_render_ai_details(
                    $aidata,
                    $OUTPUT,
                    $filemap,
                    ($assign->rubricmode ?? '') === 'custom'
                );
            }
        }
    }
}

echo html_writer::end_tag('div'); // airagassign-result-page.
echo $OUTPUT->footer();

/**
 * Render AI response details (criterion scores, citations, retrieved docs).
 *
 * @param array  $aidata   Decoded AI response
 * @param core_renderer $OUTPUT The output renderer
 * @param array  $filemap  Map of filename => ['title'=>..., 'url'=>...] for material lookup
 * @param bool   $showcriterionscores Whether to show rubric criterion scores
 */
function airagassign_render_ai_details($aidata, $OUTPUT, array $filemap = [], bool $showcriterionscores = true) {
    // Criterion scores.
    $criterionscores = $aidata['criterion_scores'] ?? [];
    if ($showcriterionscores && !empty($criterionscores)) {
        echo html_writer::start_tag('div', ['class' => 'mt-3 mb-3']);
        echo html_writer::tag('p', get_string('criteriascores', 'airagassign'),
            ['class' => 'airag-section-title mb-2']);
        echo html_writer::start_tag('div', ['class' => 'airag-table-scroll']);
        echo html_writer::start_tag('table', ['class' => 'table table-sm table-bordered mb-0']);
        echo html_writer::start_tag('thead', ['class' => 'table-light']);
        echo html_writer::tag('tr',
            html_writer::tag('th', get_string('criterion', 'airagassign'), ['style' => 'width:25%']) .
            html_writer::tag('th', get_string('score', 'airagassign'), ['style' => 'width:10%']) .
            html_writer::tag('th', get_string('feedback', 'airagassign'))
        );
        echo html_writer::end_tag('thead');
        echo html_writer::start_tag('tbody');
        foreach ($criterionscores as $cname => $cdata) {
            $cscore    = is_array($cdata) ? ($cdata['score']    ?? '-') : $cdata;
            $cfeedback = is_array($cdata) ? ($cdata['feedback'] ?? '') : '';
            echo html_writer::tag('tr',
                html_writer::tag('td', html_writer::tag('span', s($cname), ['class' => 'fw-semibold'])) .
                html_writer::tag('td', is_numeric($cscore) ? format_float($cscore, 2) : s($cscore)) .
                html_writer::tag('td', s($cfeedback), ['class' => 'text-muted small'])
            );
        }
        echo html_writer::end_tag('tbody');
        echo html_writer::end_tag('table');
        echo html_writer::end_tag('div');
        echo html_writer::end_tag('div');
    }

    // Citations.
    $citations = $aidata['citations'] ?? [];
    if (!empty($citations)) {
        echo html_writer::start_tag('div', ['class' => 'mt-2 mb-3']);
        echo html_writer::tag('p', get_string('citations', 'airagassign'),
            ['class' => 'airag-section-title mb-2']);
        echo html_writer::start_tag('div', ['class' => 'airag-citation-list']);
        foreach ($citations as $idx => $cit) {
            $text   = is_array($cit) ? ($cit['text']   ?? '') : (string)$cit;
            $source = is_array($cit) ? ($cit['source'] ?? 'Unknown') : 'Unknown';
            $page   = is_array($cit) ? ($cit['page']   ?? null) : null;

            // Resolve filename → material title + URL via filemap.
            $srcbase  = basename($source);
            $matinfo  = $filemap[$source] ?? $filemap[$srcbase] ?? null;
            $mattitle = $matinfo ? $matinfo['title'] : $source;
            $maturl   = $matinfo ? $matinfo['url']   : null;

            // Optional page badge.
            $pagebadge = '';
            if ($page !== null && $page !== '' && strtolower((string)$page) !== 'n/a') {
                $pagebadge = ' ' . html_writer::tag('span',
                    get_string('page', 'airagassign') . ' ' . s((string)$page),
                    ['class' => 'badge airag-badge-muted ms-1']);
            }

            // File-type icon derived from source filename extension.
            $iconname   = mimeinfo('icon', $srcbase ?: 'file.bin');
            $fileicon   = $OUTPUT->pix_icon(
                'f/' . $iconname,
                $iconname,
                'moodle',
                ['class' => 'iconsmall me-0']
            );

            // Source display: icon + linked title if material found, plain text otherwise.
            $srclabel   = $fileicon . s($mattitle);
            $sourcetext = $maturl
                ? html_writer::link($maturl, $srclabel,
                    ['target' => '_blank', 'title' => s($source),
                     'class'  => '.airag-citation-source'])
                : html_writer::tag('span', $srclabel);

            $numtag  = html_writer::tag('span', (string)($idx + 1), ['class' => 'airag-citation-num']);
            $quote   = html_writer::tag('span', '"' . s($text) . '"',
                ['class' => 'airag-citation-quote']);
            $srctag  = html_writer::tag('span',
                $sourcetext . $pagebadge,
                ['class' => 'airag-citation-source']);

            echo html_writer::tag('div',
                $numtag .
                html_writer::tag('div', $quote . $srctag, ['class' => 'airag-citation-body']),
                ['class' => 'airag-citation-item']
            );
        }
        echo html_writer::end_tag('div');
        echo html_writer::end_tag('div');
    }
}
