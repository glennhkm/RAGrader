<?php
// This file is part of Moodle - https://moodle.org/
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
// along with Moodle.  If not, see <https://www.gnu.org/licenses/>.

/**
 * Review page for local_assign_ai_rag.
 *
 * @package     local_assign_ai_rag
 * @copyright   2025 Glenn H. K. M.
 * @license     https://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

use local_assign_ai_rag\assign_submission;
use local_assign_ai_rag\api\client;

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
require_once($CFG->dirroot . '/mod/assign/locallib.php');
require_once($CFG->dirroot . '/local/assign_ai_rag/locallib.php');

try {
    $cmid = required_param('id', PARAM_INT);
    $action = optional_param('action', '', PARAM_ALPHA);
    $pendingid = optional_param('pendingid', 0, PARAM_INT);

    // Get the course module and the course.
    $cm = get_coursemodule_from_id('assign', $cmid, 0, false, MUST_EXIST);
    $course = $DB->get_record('course', ['id' => $cm->course], '*', MUST_EXIST);
    $context = context_module::instance($cm->id);

    // Ensure login linked to the module for proper navigation integration.
    require_login($course, true, $cm);

    require_capability('local/assign_ai_rag:review', $context);

    // Instantiate the assign object.
    $assign = new assign($context, $cm, $course);

    // Handle "Review with AI" action.
    if ($action === 'reviewai' && $pendingid > 0) {
        require_sesskey();
        
        $pending = $DB->get_record('local_assign_ai_rag_pending', ['id' => $pendingid], '*', MUST_EXIST);
        
        // Update status to processing.
        $DB->set_field('local_assign_ai_rag_pending', 'status', assign_submission::STATUS_PROCESSING, ['id' => $pendingid]);
        
        try {
            // Process with RAG AI.
            $submission = new assign_submission($pending->userid, $assign);
            $submission->process_submission_ai_review($pendingid);
            
            \core\notification::success(get_string('reviewsuccess', 'local_assign_ai_rag'));
        } catch (\Exception $e) {
            // Reset status on error.
            $DB->set_field('local_assign_ai_rag_pending', 'status', assign_submission::STATUS_INITIAL, ['id' => $pendingid]);
            \core\notification::error(get_string('reviewerror', 'local_assign_ai_rag') . ': ' . $e->getMessage());
        }
        
        // Redirect back to review page.
        redirect(new moodle_url('/local/assign_ai_rag/review.php', ['id' => $cmid]));
    }

    // Sync existing submissions to pending table (for submissions made before plugin install).
    local_assign_ai_rag_sync_existing_submissions($cmid);

    // Validate RAG server configuration.
    $serverurl = get_config('local_assign_ai_rag', 'server_url');
    if (empty($serverurl)) {
        \core\notification::warning(get_string('serverunavailable', 'local_assign_ai_rag'));
    }

    // Check materials count.
    $materialscount = local_assign_ai_rag_get_materials_count($course->id);

    // Page configuration.
    $PAGE->set_url(new moodle_url('/local/assign_ai_rag/review.php', ['id' => $cmid]));
    $PAGE->set_course($course);
    $PAGE->set_context($context);
    $PAGE->set_title(get_string('reviewwithai', 'local_assign_ai_rag'));
    $PAGE->set_heading(format_string($course->fullname));

    $PAGE->activityheader->disable();

    echo $OUTPUT->header();

    // Get the list of enrolled users with submission capability.
    $students = get_enrolled_users($context, 'mod/assign:submit');

    $pendingcount = $DB->count_records('local_assign_ai_rag_pending', [
        'courseid' => $course->id,
        'assignmentid' => $cm->id,
        'status' => assign_submission::STATUS_INITIAL,
    ]);
    $allblocked = ($pendingcount === 0);
    $hasinitial = ($pendingcount > 0);

    $pendingforapprove = $DB->count_records('local_assign_ai_rag_pending', [
        'courseid' => $course->id,
        'assignmentid' => $cm->id,
        'status' => assign_submission::STATUS_PENDING,
    ]);
    $haspending = ($pendingforapprove > 0);

    $rows = [];

    // Build table from records with statuses relevant to the workflow.
    $statuses = [
        assign_submission::STATUS_INITIAL,
        assign_submission::STATUS_QUEUED,
        assign_submission::STATUS_PROCESSING,
        assign_submission::STATUS_PENDING,
    ];
    [$insql, $inparams] = $DB->get_in_or_equal($statuses, SQL_PARAMS_NAMED, 'st');
    $select = "courseid = :courseid AND assignmentid = :assignmentid AND status $insql";
    $inparams['courseid'] = $course->id;
    $inparams['assignmentid'] = $cm->id;
    $pendings = $DB->get_records_select('local_assign_ai_rag_pending', $select, $inparams, 'timemodified DESC, id DESC');

    foreach ($pendings as $record) {
        $student = $DB->get_record('user', ['id' => $record->userid], '*', MUST_EXIST);

        // Submission info.
        $submission = $assign->get_user_submission($student->id, false);
        if ($submission) {
            switch ($submission->status) {
                case 'submitted':
                    $status = get_string('approved', 'local_assign_ai_rag');
                    break;
                case 'draft':
                    $status = get_string('pending', 'local_assign_ai_rag');
                    break;
                default:
                    $status = get_string('initial', 'local_assign_ai_rag');
            }
        } else {
            $status = get_string('initial', 'local_assign_ai_rag');
        }

        $lastmodified = '-';
        $filesout = [];
        if ($submission) {
            if (!empty($submission->timemodified)) {
                $lastmodified = userdate($submission->timemodified);
            }
            $fs = get_file_storage();
            $files = $fs->get_area_files(
                $assign->get_context()->id,
                'assignsubmission_file',
                'submission_files',
                $submission->id,
                'id',
                false
            );
            if ($files) {
                foreach ($files as $file) {
                    $url = moodle_url::make_pluginfile_url(
                        $file->get_contextid(),
                        $file->get_component(),
                        $file->get_filearea(),
                        $file->get_itemid(),
                        $file->get_filepath(),
                        $file->get_filename()
                    );
                    $filesout[] = [
                        'url' => $url->out(false),
                        'name' => $file->get_filename(),
                    ];
                }
            }
        }

        $grade = $record->grade !== null ? format_float((float)$record->grade, 2, true, true) : '-';
        $confidence = $record->confidence !== null ? round($record->confidence * 100) . '%' : '-';
        $inprogress = $record->status === assign_submission::STATUS_PROCESSING;
        $isinitial = ($record->status === assign_submission::STATUS_INITIAL);
        $isqueued = ($record->status === assign_submission::STATUS_QUEUED);
        $isprocessing = ($record->status === assign_submission::STATUS_PROCESSING);
        $ispending = ($record->status === assign_submission::STATUS_PENDING);

        if ($isinitial) {
            $statebadge = get_string('initial', 'local_assign_ai_rag');
            $statebadgeclass = 'badge bg-secondary';
            $canrequestai = true;
            $canapproveai = false;
        } else if ($isqueued) {
            $statebadge = get_string('queued', 'local_assign_ai_rag');
            $statebadgeclass = 'badge bg-warning';
            $canrequestai = false;
            $canapproveai = false;
        } else if ($isprocessing) {
            $statebadge = get_string('processing', 'local_assign_ai_rag');
            $statebadgeclass = 'badge bg-warning';
            $canrequestai = false;
            $canapproveai = false;
        } else {
            $statebadge = get_string('pending', 'local_assign_ai_rag');
            $statebadgeclass = 'badge bg-info';
            $canrequestai = false;
            $canapproveai = true;
        }

        $graderurl = new moodle_url('/mod/assign/view.php', [
            'id' => $cmid,
            'action' => 'grader',
            'userid' => $student->id,
        ]);

        // Parse citations if available.
        $citations = [];
        if (!empty($record->citations)) {
            $citations = json_decode($record->citations, true) ?? [];
        }

        $rows[] = [
            'fullname' => fullname($student),
            'email' => $student->email,
            'status' => $status,
            'lastmodified' => $lastmodified,
            'files' => $filesout,
            'grade' => $grade,
            'confidence' => $confidence,
            'citations' => $citations,
            'hascitations' => !empty($citations),
            'isinitial' => $isinitial,
            'ispending' => $ispending,
            'isqueued' => $isqueued,
            'inprogress' => $inprogress,
            'aistatus' => $record->status,
            'canrequestai' => $canrequestai,
            'canapproveai' => $canapproveai,
            'statebadge' => $statebadge,
            'statebadgeclass' => $statebadgeclass,
            'courseid' => $course->id,
            'cmid' => $cmid,
            'userid' => $student->id,
            'pendingid' => $record->id,
            'graderurl' => $graderurl->out(false),
            'feedback' => $record->message,
        ];
    }

    // Build template context.
    $templatecontext = [
        'backurl' => (new moodle_url('/course/view.php', ['id' => $course->id]))->out(false),
        'rows' => $rows,
        'allblocked' => $allblocked,
        'hasinitial' => $hasinitial,
        'haspending' => $haspending,
        'cmid' => $cmid,
        'courseid' => $course->id,
        'materialscount' => $materialscount,
        'materialsurl' => (new moodle_url('/local/assign_ai_rag/materials.php', ['courseid' => $course->id]))->out(false),
        'hasrows' => !empty($rows),
        'nosubmissions' => empty($rows),
    ];

    // Simple output without template for now.
    echo '<div class="container-fluid">';
    echo '<div class="row mb-3">';
    echo '<div class="col">';
    echo '<a href="' . $templatecontext['backurl'] . '" class="btn btn-secondary">&larr; Back to Course</a>';
    echo ' <a href="' . $templatecontext['materialsurl'] . '" class="btn btn-outline-primary">📚 Course Materials (' . $materialscount . ')</a>';
    $rubricurl = new moodle_url('/local/assign_ai_rag/rubric.php', ['id' => $cmid]);
    echo ' <a href="' . $rubricurl->out(false) . '" class="btn btn-outline-info">📋 ' . get_string('editrubric', 'local_assign_ai_rag') . '</a>';
    echo '</div>';
    echo '</div>';
    
    echo '<h2>' . get_string('reviewpagetitle', 'local_assign_ai_rag') . '</h2>';
    
    if (empty($rows)) {
        echo '<div class="alert alert-info">' . get_string('nosubmissions', 'local_assign_ai_rag') . '</div>';
    } else {
        echo '<table class="table table-striped">';
        echo '<thead><tr>';
        echo '<th>' . get_string('student', 'local_assign_ai_rag') . '</th>';
        echo '<th>' . get_string('submissionstatus', 'local_assign_ai_rag') . '</th>';
        echo '<th>' . get_string('aistatus', 'local_assign_ai_rag') . '</th>';
        echo '<th>' . get_string('aigrade', 'local_assign_ai_rag') . '</th>';
        echo '<th>' . get_string('confidence', 'local_assign_ai_rag') . '</th>';
        echo '<th>' . get_string('actions', 'local_assign_ai_rag') . '</th>';
        echo '</tr></thead><tbody>';
        
        foreach ($rows as $row) {
            echo '<tr>';
            echo '<td>' . s($row['fullname']) . '<br><small class="text-muted">' . s($row['email']) . '</small></td>';
            echo '<td>' . s($row['status']) . '</td>';
            echo '<td><span class="' . $row['statebadgeclass'] . '">' . s($row['statebadge']) . '</span></td>';
            echo '<td>' . s($row['grade']) . '</td>';
            echo '<td>' . s($row['confidence']) . '</td>';
            echo '<td>';
            if ($row['canrequestai']) {
                $reviewurl = new moodle_url('/local/assign_ai_rag/review.php', [
                    'id' => $cmid,
                    'action' => 'reviewai',
                    'pendingid' => $row['pendingid'],
                    'sesskey' => sesskey(),
                ]);
                echo '<a href="' . $reviewurl->out(false) . '" class="btn btn-sm btn-primary">Review with AI</a> ';
            }
            if ($row['canapproveai']) {
                $viewresulturl = new moodle_url('/local/assign_ai_rag/view_result.php', ['pendingid' => $row['pendingid']]);
                echo '<a href="' . $viewresulturl->out(false) . '" class="btn btn-sm btn-success">' . get_string('approve', 'local_assign_ai_rag') . '</a> ';
            }
            $viewresulturl = new moodle_url('/local/assign_ai_rag/view_result.php', ['pendingid' => $row['pendingid']]);
            echo '<a href="' . $viewresulturl->out(false) . '" class="btn btn-sm btn-outline-secondary">' . get_string('viewdetails', 'local_assign_ai_rag') . '</a>';
            echo '</td>';
            echo '</tr>';
        }
        
        echo '</tbody></table>';
    }
    
    echo '</div>';

    echo $OUTPUT->footer();
} catch (Exception $e) {
    \core\notification::error('Error: ' . $e->getMessage());
    echo $OUTPUT->footer();
}
