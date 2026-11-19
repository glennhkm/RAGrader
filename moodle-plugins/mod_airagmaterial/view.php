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
 * View page for AI RAG Material.
 *
 * @package    mod_airagmaterial
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

$id = optional_param('id', 0, PARAM_INT); // Course module ID.
$m = optional_param('m', 0, PARAM_INT);   // Instance ID.
$action = optional_param('action', '', PARAM_ALPHA); // vectorize, clear.

if ($id) {
    $cm = get_coursemodule_from_id('airagmaterial', $id, 0, false, MUST_EXIST);
    $course = get_course($cm->course);
    $material = $DB->get_record('airagmaterial', ['id' => $cm->instance], '*', MUST_EXIST);
} else if ($m) {
    $material = $DB->get_record('airagmaterial', ['id' => $m], '*', MUST_EXIST);
    $course = get_course($material->course);
    $cm = get_coursemodule_from_instance('airagmaterial', $material->id, $course->id, false, MUST_EXIST);
} else {
    throw new moodle_exception('missingparameter');
}

require_login($course, true, $cm);
$context = context_module::instance($cm->id);
require_capability('mod/airagmaterial:view', $context);

// Trigger view event.
$event = \mod_airagmaterial\event\course_module_viewed::create([
    'objectid' => $material->id,
    'context' => $context,
]);
$event->add_record_snapshot('course_modules', $cm);
$event->add_record_snapshot('airagmaterial', $material);
$event->trigger();

$canmanage = has_capability('mod/airagmaterial:manage', $context);

// ── Auto-vectorize: notify that background task was queued ──────────────────
global $SESSION;
if (!empty($SESSION->airagmaterial_autovectorize)
        && (int)$SESSION->airagmaterial_autovectorize['materialid'] === (int)$material->id) {
    unset($SESSION->airagmaterial_autovectorize);
    // Reload material so status table reflects current state.
    $material = $DB->get_record('airagmaterial', ['id' => $material->id], '*', MUST_EXIST);
    \core\notification::info(get_string('vectorize_queued_notice', 'airagmaterial'));
}

// Handle actions (vectorize / clear).
if ($canmanage && $action && confirm_sesskey()) {
    if ($action === 'vectorize') {
        require_once($CFG->dirroot . '/mod/airagmaterial/lib.php');
        // Queue background task — returns immediately to the teacher.
        airagmaterial_queue_vectorize_task($material, $context->id);
        // Reload record so the status badge updates to 'queued' on this page load.
        $material = $DB->get_record('airagmaterial', ['id' => $material->id], '*', MUST_EXIST);
        \core\notification::info(get_string('vectorize_queued_notice', 'airagmaterial'));
    } else if ($action === 'clearvectors') {
        require_once($CFG->dirroot . '/mod/airagmaterial/lib.php');

        if (in_array($material->vectorize_status, ['queued', 'processing'], true)) {
            // A running vectorization task would re-create the vectors right away.
            \core\notification::warning(get_string('clearvectors_busy', 'airagmaterial'));
        } else {
            // Remove only this material's files from the course collection. Clearing
            // the whole course collection would also wipe other materials and
            // assignment reference files while their status still says 'completed'.
            $cleanup = airagmaterial_delete_material_vectors($material,
                airagmaterial_get_tracked_filenames((int)$material->id));

            $handled = array_merge($cleanup['deleted'], $cleanup['retained']);
            if (!empty($handled)) {
                [$insql, $params] = $DB->get_in_or_equal($handled, SQL_PARAMS_NAMED, 'fn');
                $params['materialid'] = $material->id;
                $DB->delete_records_select('airagmaterial_files', "materialid = :materialid AND filename $insql", $params);
            }

            $material->chunks_created = 0;
            $material->documents_loaded = 0;
            $material->total_in_db = 0;
            if (empty($cleanup['failed'])) {
                $material->vectorize_status = 'pending';
                $material->vectorize_error = null;
                \core\notification::success(get_string('clearvectors_success', 'airagmaterial'));
            } else {
                // Keep the failed files tracked so the teacher can retry, and take the
                // material out of 'completed' so assignments stop using it meanwhile.
                $material->vectorize_status = 'failed';
                $material->vectorize_error = get_string('clearvectors_failed', 'airagmaterial',
                    implode(', ', $cleanup['failed']));
                \core\notification::warning($material->vectorize_error);
            }
            $DB->update_record('airagmaterial', $material);

            if (!empty($cleanup['retained'])) {
                \core\notification::info(get_string('clearvectors_retained', 'airagmaterial',
                    implode(', ', $cleanup['retained'])));
            }
        }
        redirect(new moodle_url('/mod/airagmaterial/view.php', ['id' => $cm->id]));
    }
}

// Page setup.
$PAGE->set_url('/mod/airagmaterial/view.php', ['id' => $cm->id]);
$PAGE->set_title(format_string($material->name));
$PAGE->set_heading(format_string($course->fullname));
$PAGE->set_activity_record($material);

echo $OUTPUT->header();
echo $OUTPUT->heading(format_string($material->name));

// Show description.
if (!empty($material->intro)) {
    echo $OUTPUT->box(format_module_intro('airagmaterial', $material, $cm->id), 'generalbox mod_introbox', 'airagmaterialintro');
}

// ---- Uploaded files section ----
echo $OUTPUT->heading(get_string('uploadedfiles', 'airagmaterial'), 3);

$uploadedfiles = airagmaterial_get_uploaded_files($context->id);
if (empty($uploadedfiles)) {
    echo $OUTPUT->notification(get_string('nofiles', 'airagmaterial'), 'info');
} else {
    echo html_writer::start_tag('div', ['class' => 'airagmaterial-files mb-3']);
    echo html_writer::start_tag('table', ['class' => 'table table-striped table-sm']);
    echo html_writer::start_tag('thead');
    echo html_writer::tag('tr',
        html_writer::tag('th', 'File') .
        html_writer::tag('th', 'Size') .
        html_writer::tag('th', 'Type')
    );
    echo html_writer::end_tag('thead');
    echo html_writer::start_tag('tbody');

    foreach ($uploadedfiles as $file) {
        $fileurl = moodle_url::make_pluginfile_url(
            $context->id, 'mod_airagmaterial', 'materials', 0,
            $file->get_filepath(), $file->get_filename()
        );
        $filesize = display_size($file->get_filesize());
        $mimetype = $file->get_mimetype();
        $icon = $OUTPUT->pix_icon(file_mimetype_icon($mimetype), $mimetype);

        echo html_writer::start_tag('tr');
        echo html_writer::tag('td', $icon . ' ' . html_writer::link($fileurl, $file->get_filename()));
        echo html_writer::tag('td', $filesize);
        echo html_writer::tag('td', $mimetype);
        echo html_writer::end_tag('tr');
    }

    echo html_writer::end_tag('tbody');
    echo html_writer::end_tag('table');
    echo html_writer::tag('p', get_string('filecount', 'airagmaterial', count($uploadedfiles)),
        ['class' => 'text-muted small']);
    echo html_writer::end_tag('div');
}

// ---- Vector status section ----
echo $OUTPUT->heading(get_string('vectorstatus', 'airagmaterial'), 3);

$statusclass = 'badge ';
switch ($material->vectorize_status) {
    case 'completed':
        $statusclass .= 'badge-success bg-success';
        break;
    case 'queued':
        $statusclass .= 'badge-warning bg-warning';
        break;
    case 'processing':
        $statusclass .= 'badge-warning bg-warning';
        break;
    case 'failed':
        $statusclass .= 'badge-danger bg-danger';
        break;
    default:
        $statusclass .= 'badge-secondary bg-secondary';
}

echo html_writer::start_tag('div', ['class' => 'airagmaterial-status mb-3']);
echo html_writer::start_tag('table', ['class' => 'table table-sm', 'style' => 'max-width:500px']);

echo html_writer::tag('tr',
    html_writer::tag('th', get_string('vectorizestatus', 'airagmaterial')) .
    html_writer::tag('td', html_writer::span(
        get_string('status_' . $material->vectorize_status, 'airagmaterial'),
        $statusclass
    ))
);

echo html_writer::tag('tr',
    html_writer::tag('th', get_string('totalchunks', 'airagmaterial')) .
    html_writer::tag('td', $material->chunks_created)
);

echo html_writer::tag('tr',
    html_writer::tag('th', get_string('totaldocuments', 'airagmaterial')) .
    html_writer::tag('td', $material->documents_loaded)
);

$lastprocessed = $material->last_vectorized > 0
    ? userdate($material->last_vectorized)
    : get_string('never', 'airagmaterial');
echo html_writer::tag('tr',
    html_writer::tag('th', get_string('lastprocessed', 'airagmaterial')) .
    html_writer::tag('td', $lastprocessed)
);

if (!empty($material->vectorize_error) && !in_array($material->vectorize_status, ['queued', 'processing'], true)) {
    echo html_writer::tag('tr',
        html_writer::tag('th', 'Error') .
        html_writer::tag('td', html_writer::tag('pre', s($material->vectorize_error),
            ['class' => 'text-danger small', 'style' => 'white-space:pre-wrap']))
    );
}

echo html_writer::end_tag('table');
echo html_writer::end_tag('div');

// ---- Per-file vectorization details ----
$trackedfiles = $DB->get_records('airagmaterial_files', ['materialid' => $material->id], 'filename ASC');
if (!empty($trackedfiles)) {
    echo html_writer::start_tag('details', ['class' => 'mb-3']);
    echo html_writer::tag('summary', 'File vectorization details', ['class' => 'btn btn-sm btn-outline-secondary mb-2']);
    echo html_writer::start_tag('table', ['class' => 'table table-sm table-bordered']);
    echo html_writer::start_tag('thead');
    echo html_writer::tag('tr',
        html_writer::tag('th', 'File') .
        html_writer::tag('th', 'Size') .
        html_writer::tag('th', 'Status') .
        html_writer::tag('th', 'Chunks')
    );
    echo html_writer::end_tag('thead');
    echo html_writer::start_tag('tbody');

    foreach ($trackedfiles as $tf) {
        $statusbadge = $tf->vectorized
            ? html_writer::span('✓ Vectorized', 'badge badge-success bg-success')
            : html_writer::span('✗ Failed', 'badge badge-danger bg-danger');
        echo html_writer::start_tag('tr');
        echo html_writer::tag('td', s($tf->filename));
        echo html_writer::tag('td', display_size($tf->filesize));
        echo html_writer::tag('td', $statusbadge);
        echo html_writer::tag('td', $tf->chunks_count);
        echo html_writer::end_tag('tr');

        if (!empty($tf->error_message)) {
            echo html_writer::tag('tr',
                html_writer::tag('td', html_writer::tag('small', s($tf->error_message), ['class' => 'text-danger']),
                    ['colspan' => '4'])
            );
        }
    }

    echo html_writer::end_tag('tbody');
    echo html_writer::end_tag('table');
    echo html_writer::end_tag('details');
}

// ---- Action buttons ----
if ($canmanage && !empty($uploadedfiles)) {
    echo html_writer::start_tag('div', ['class' => 'airagmaterial-actions mt-3']);

    // ── Polling banner: shown when vectorization is queued or in progress ────
    $isbusy = in_array($material->vectorize_status, ['queued', 'processing']);
    $statusdisplay = get_string('status_' . ($material->vectorize_status ?? 'pending'), 'airagmaterial');
    echo html_writer::tag('div',
        html_writer::tag('div',
            html_writer::tag('span', '', ['class' => 'spinner-border spinner-border-sm me-2', 'role' => 'status', 'aria-hidden' => 'true']) .
            html_writer::tag('strong', get_string('vectorize_processing_title', 'airagmaterial')) .
            html_writer::tag('span', ' — ' . get_string('queue_navigate_away', 'airagmaterial'), ['class' => 'ms-1']),
            ['class' => 'airag-queue-banner-inner d-flex align-items-center']
        ),
        [
            'id'    => 'airag-vectorize-busy-banner',
            'class' => 'alert alert-info d-flex align-items-center mb-3' . ($isbusy ? '' : ' d-none'),
            'style' => $isbusy ? '' : 'display:none!important',
        ]
    );

    // Info: vectorization is automatic.
    echo html_writer::tag('p',
        get_string('autovectorize_info', 'airagmaterial'),
        ['class' => 'text-muted small mb-2']);

    // Re-vectorize button — always available so teacher can reprocess if needed.
    $vectorizeurl = new moodle_url('/mod/airagmaterial/view.php', [
        'id'      => $cm->id,
        'action'  => 'vectorize',
        'sesskey' => sesskey(),
    ]);
    echo html_writer::link($vectorizeurl,
        get_string('revectorize', 'airagmaterial'),
        ['class' => 'btn btn-primary mr-2 me-2']);

    // Clear vectors button — whenever this material still tracks files and no
    // vectorization task is running.
    if (!$isbusy && $DB->record_exists('airagmaterial_files', ['materialid' => $material->id])) {
        $clearurl = new moodle_url('/mod/airagmaterial/view.php', [
            'id'      => $cm->id,
            'action'  => 'clearvectors',
            'sesskey' => sesskey(),
        ]);
        echo html_writer::link($clearurl, get_string('clearvectors', 'airagmaterial'),
            ['class' => 'btn btn-danger',
             'onclick' => 'return confirm(' . json_encode(get_string('confirmclear', 'airagmaterial')) . ');']);
    }

    echo html_writer::end_tag('div');
}

echo $OUTPUT->footer();
// ── Polling JS: auto-refresh when vectorization is queued / in progress ──────
$statusurl = (new moodle_url('/mod/airagmaterial/status.php', ['id' => $cm->id]))->out(false);
$isbusy    = in_array($material->vectorize_status, ['queued', 'processing']) ? 'true' : 'false';
echo <<<HTML
<script>
(function () {
    var busy   = {$isbusy};
    var banner = document.getElementById('airag-vectorize-busy-banner');
    if (!busy) return;           // nothing to poll

    function showBanner(show) {
        if (!banner) return;
        if (show) {
            banner.style.removeProperty('display');
            banner.classList.remove('d-none');
        } else {
            banner.style.display = 'none';
        }
    }
    showBanner(true);

    var interval = setInterval(function () {
        fetch('{$statusurl}', {credentials: 'same-origin'})
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.busy) {
                    clearInterval(interval);
                    // Reload page to reflect completed/failed status.
                    window.location.reload();
                }
            })
            .catch(function () { /* network error: keep polling */ });
    }, 5000);
})();
</script>
HTML;
