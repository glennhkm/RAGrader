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
 * Student submission page for AI RAG Assignment.
 *
 * @package    mod_airagassign
 * @copyright  2025 Glenn HKM
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

// Resolve Moodle config for standard, symlinked, and public directory layouts.
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
    require_once(__DIR__ . '/../../config.php');
}

$id = required_param('id', PARAM_INT);

$cm = get_coursemodule_from_id('airagassign', $id, 0, false, MUST_EXIST);
$course = get_course($cm->course);
$assign = $DB->get_record('airagassign', ['id' => $cm->instance], '*', MUST_EXIST);

require_login($course, true, $cm);
$context = context_module::instance($cm->id);
require_capability('mod/airagassign:submit', $context);

$returnurl = new moodle_url('/mod/airagassign/view.php', ['id' => $cm->id]);
$submiturl = new moodle_url('/mod/airagassign/submit.php', ['id' => $cm->id]);

// Only one submission is allowed for this activity.
$existing = $DB->get_record('airagassign_submissions', [
    'assignid' => $assign->id,
    'userid' => $USER->id,
]);
if ($existing) {
    redirect($returnurl, get_string('alreadysubmitted', 'airagassign'));
}

$now = time();
if ($assign->opendate > 0 && $assign->opendate > $now) {
    redirect($returnurl,
        get_string('notavailableyet', 'airagassign', userdate($assign->opendate)));
}

$isclosed = ($assign->duedate > 0 && $assign->duedate < $now && !$assign->allowlate);
if ($isclosed) {
    redirect($returnurl, get_string('notallowedsinceclosed', 'airagassign'));
}

// A submission requires either a completed linked material or a manual file.
$fs = get_file_storage();
$manualfiles = $fs->get_area_files(
    $context->id,
    'mod_airagassign',
    'manualfile',
    0,
    'id',
    false
);
$hasmanualfile = !empty($manualfiles);
$validmaterialcount = $DB->count_records_sql(
    "SELECT COUNT(*)
       FROM {airagassign_materials} am
       JOIN {airagmaterial} m ON m.id = am.materialid
      WHERE am.assignid = :assignid
        AND m.vectorize_status = 'completed'",
    ['assignid' => $assign->id]
);
if ($validmaterialcount == 0 && !$hasmanualfile) {
    redirect(
        $returnurl,
        get_string('nomaterialsavailable', 'airagassign'),
        null,
        \core\output\notification::NOTIFY_WARNING
    );
}

$PAGE->set_url($submiturl);
$PAGE->set_title(format_string($assign->name) . ' - ' .
    get_string('submitanswers', 'airagassign'));
$PAGE->set_heading(format_string($course->fullname));

$questions = [];
if ($assign->assignmode === 'quiz') {
    $questions = $DB->get_records(
        'airagassign_questions',
        ['assignid' => $assign->id],
        'sortorder ASC'
    );
}

$values = [];
$errors = [];

// Use explicit semantic markup instead of MoodleQuickForm here. Several Moodle
// 4.5 themes alter QuickForm's grid wrappers, which can move controls out of
// normal document flow. Permission, CSRF, and validation remain server-side.
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    require_sesskey();

    if ($assign->assignmode === 'quiz') {
        foreach ($questions as $question) {
            $fieldname = 'answer_' . $question->id;
            $values[$fieldname] = trim(optional_param($fieldname, '', PARAM_TEXT));
            if ($values[$fieldname] === '') {
                $errors[$fieldname] = get_string('required');
            }
        }
    } else {
        $values['essay'] = trim(optional_param('essay', '', PARAM_TEXT));
        if ($values['essay'] === '') {
            $errors['essay'] = get_string('required');
        } else {
            $wordcount = count(preg_split(
                '/\s+/',
                $values['essay'],
                -1,
                PREG_SPLIT_NO_EMPTY
            ));
            if ($assign->minwords > 0 && $wordcount < $assign->minwords) {
                $errors['essay'] = get_string(
                    'wordcountbelowmin',
                    'airagassign',
                    $assign->minwords
                );
            } else if ($assign->maxwords > 0 && $wordcount > $assign->maxwords) {
                $errors['essay'] = get_string(
                    'wordcountabovemax',
                    'airagassign',
                    $assign->maxwords
                );
            }
        }
    }

    if (empty($errors)) {
        $transaction = $DB->start_delegated_transaction();

        $submission = (object) [
            'assignid' => $assign->id,
            'userid' => $USER->id,
            'status' => 'submitted',
            'timecreated' => time(),
            'timegraded' => 0,
        ];
        $submission->id = $DB->insert_record('airagassign_submissions', $submission);

        if ($assign->assignmode === 'quiz') {
            foreach ($questions as $question) {
                $fieldname = 'answer_' . $question->id;
                $answer = (object) [
                    'submissionid' => $submission->id,
                    'questionid' => $question->id,
                    'answertext' => $values[$fieldname],
                    'timecreated' => time(),
                ];
                $DB->insert_record('airagassign_answers', $answer);
            }
        } else {
            $answer = (object) [
                'submissionid' => $submission->id,
                'questionid' => null,
                'answertext' => $values['essay'],
                'timecreated' => time(),
            ];
            $DB->insert_record('airagassign_answers', $answer);
        }

        $transaction->allow_commit();
        redirect(
            $returnurl,
            get_string('submissionsaved', 'airagassign'),
            null,
            \core\output\notification::NOTIFY_SUCCESS
        );
    }
}

$PAGE->requires->css('/mod/airagassign/styles.css');
echo $OUTPUT->header();
echo html_writer::start_tag('div', ['class' => 'airagassign-submit-page']);
echo $OUTPUT->heading(format_string($assign->name) . ' - ' .
    get_string('submitanswers', 'airagassign'));

// Show the activity-built-in rubric as a read-only reference.
$criteria = [];
if (($assign->rubricmode ?? '') === 'custom') {
    $criteria = $DB->get_records(
        'airagassign_criteria',
        ['assignid' => $assign->id],
        'sortorder ASC'
    );
}
if (!empty($criteria)) {
    echo html_writer::start_tag('details', [
        'class' => 'airagassign-rubric mb-4',
        'open' => '',
    ]);
    echo html_writer::tag(
        'summary',
        get_string('rubricinfo', 'airagassign'),
        ['class' => 'btn btn-sm btn-airag-outline-info mb-2']
    );
    echo html_writer::start_tag('div', ['class' => 'airag-table-scroll']);
    echo html_writer::start_tag('table', [
        'class' => 'table table-sm table-bordered airagassign-rubric-table',
    ]);
    echo html_writer::start_tag('thead');
    echo html_writer::tag('tr',
        html_writer::tag('th', get_string('criterionname', 'airagassign')) .
        html_writer::tag('th', get_string('criteriondesc', 'airagassign')) .
        html_writer::tag('th', get_string('criterionmaxscore', 'airagassign'))
    );
    echo html_writer::end_tag('thead');
    echo html_writer::start_tag('tbody');
    foreach ($criteria as $criterion) {
        echo html_writer::tag('tr',
            html_writer::tag('td', s($criterion->name)) .
            html_writer::tag('td', s($criterion->description)) .
            html_writer::tag('td', format_float($criterion->maxscore, 2))
        );
    }
    echo html_writer::end_tag('tbody');
    echo html_writer::end_tag('table');
    echo html_writer::end_tag('div');
    echo html_writer::end_tag('details');
}

echo html_writer::start_tag('form', [
    'method' => 'post',
    'action' => $submiturl,
    'class' => 'airagassign-answer-form',
    'id' => 'airagassign-answer-form',
]);
echo html_writer::empty_tag('input', [
    'type' => 'hidden',
    'name' => 'sesskey',
    'value' => sesskey(),
]);

if ($assign->assignmode === 'quiz') {
    $questionnumber = 1;
    foreach ($questions as $question) {
        $fieldname = 'answer_' . $question->id;
        $fieldid = 'id_' . $fieldname;
        $errorid = $fieldid . '_error';
        $haserror = isset($errors[$fieldname]);

        echo html_writer::start_tag('section', ['class' => 'airag-answer-item']);
        echo html_writer::tag('div',
            html_writer::tag('strong',
                get_string('questiontext', 'airagassign', $questionnumber)) .
            html_writer::tag('div',
                format_text($question->questiontext, FORMAT_MOODLE),
                ['class' => 'airag-question-text']),
            ['class' => 'airag-question-prompt']
        );
        echo html_writer::tag(
            'label',
            get_string('youranswer', 'airagassign'),
            ['class' => 'airag-field-label', 'for' => $fieldid]
        );

        $attributes = [
            'id' => $fieldid,
            'name' => $fieldname,
            'class' => 'airag-answer-textarea' . ($haserror ? ' is-invalid' : ''),
            'rows' => 7,
            'required' => 'required',
            'aria-required' => 'true',
        ];
        if ($haserror) {
            $attributes['aria-invalid'] = 'true';
            $attributes['aria-describedby'] = $errorid;
        }
        echo html_writer::tag(
            'textarea',
            s($values[$fieldname] ?? ''),
            $attributes
        );
        if ($haserror) {
            echo html_writer::tag('div', s($errors[$fieldname]), [
                'class' => 'airag-field-error',
                'id' => $errorid,
                'role' => 'alert',
            ]);
        }
        echo html_writer::end_tag('section');
        $questionnumber++;
    }
} else {
    if (!empty($assign->essayprompt)) {
        echo html_writer::tag('div',
            html_writer::tag('strong', get_string('essayprompt', 'airagassign')) .
            html_writer::tag('div',
                format_text($assign->essayprompt, FORMAT_MOODLE),
                ['class' => 'airag-question-text']),
            ['class' => 'airag-question-prompt']
        );
    }

    $haserror = isset($errors['essay']);
    echo html_writer::start_tag('section', ['class' => 'airag-answer-item']);
    echo html_writer::tag(
        'label',
        get_string('youressay', 'airagassign'),
        ['class' => 'airag-field-label', 'for' => 'id_essay']
    );
    $attributes = [
        'id' => 'id_essay',
        'name' => 'essay',
        'class' => 'airag-answer-textarea' . ($haserror ? ' is-invalid' : ''),
        'rows' => 15,
        'required' => 'required',
        'aria-required' => 'true',
    ];
    if ($haserror) {
        $attributes['aria-invalid'] = 'true';
        $attributes['aria-describedby'] = 'id_essay_error';
    }
    echo html_writer::tag('textarea', s($values['essay'] ?? ''), $attributes);
    if ($haserror) {
        echo html_writer::tag('div', s($errors['essay']), [
            'class' => 'airag-field-error',
            'id' => 'id_essay_error',
            'role' => 'alert',
        ]);
    }

    if ($assign->minwords > 0 || $assign->maxwords > 0) {
        $wordlimits = [];
        if ($assign->minwords > 0) {
            $wordlimits[] = get_string('minwords', 'airagassign') . ': ' .
                (int) $assign->minwords;
        }
        if ($assign->maxwords > 0) {
            $wordlimits[] = get_string('maxwords', 'airagassign') . ': ' .
                (int) $assign->maxwords;
        }
        echo html_writer::tag(
            'small',
            implode(' | ', $wordlimits),
            ['class' => 'airag-word-limits']
        );
    }
    echo html_writer::end_tag('section');
}

echo html_writer::start_tag('div', ['class' => 'airag-action-row airag-submit-actions']);
echo html_writer::tag(
    'button',
    get_string('submitanswers', 'airagassign'),
    [
        'type' => 'submit',
        'class' => 'btn btn-airag-primary btn-lg',
        'id' => 'airagassign-submit-button',
    ]
);
echo html_writer::link(
    $returnurl,
    get_string('cancel', 'core'),
    ['class' => 'btn btn-airag-outline-secondary btn-lg']
);
echo html_writer::end_tag('div');
echo html_writer::end_tag('form');

echo html_writer::end_tag('div');

echo <<<'JS'
<script>
(function () {
    'use strict';
    var form = document.getElementById('airagassign-answer-form');
    var button = document.getElementById('airagassign-submit-button');
    if (!form || !button) {
        return;
    }
    form.addEventListener('submit', function () {
        button.disabled = true;
        button.setAttribute('aria-busy', 'true');
    });
})();
</script>
JS;

echo $OUTPUT->footer();
