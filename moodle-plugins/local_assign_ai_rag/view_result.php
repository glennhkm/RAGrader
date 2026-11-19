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
 * View detailed RAG grading result page.
 *
 * @package     local_assign_ai_rag
 * @copyright   2025 Glenn H. K. M.
 * @license     https://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

use local_assign_ai_rag\assign_submission;

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

$pendingid = required_param('pendingid', PARAM_INT);
$action = optional_param('action', '', PARAM_ALPHA);

// Get pending record.
$pending = $DB->get_record('local_assign_ai_rag_pending', ['id' => $pendingid], '*', MUST_EXIST);
$cmid = $pending->assignmentid;

// Get the course module and the course.
$cm = get_coursemodule_from_id('assign', $cmid, 0, false, MUST_EXIST);
$course = $DB->get_record('course', ['id' => $cm->course], '*', MUST_EXIST);
$context = context_module::instance($cm->id);

require_login($course, true, $cm);
require_capability('local/assign_ai_rag:review', $context);

// Instantiate the assign object.
$assign = new assign($context, $cm, $course);
$assignment = $assign->get_instance();

// Get student info.
$student = $DB->get_record('user', ['id' => $pending->userid], '*', MUST_EXIST);

// Handle approve action.
if ($action === 'approve' && $pending->status === assign_submission::STATUS_PENDING) {
    require_sesskey();
    
    // Apply grade and feedback to Moodle.
    local_assign_ai_rag_apply_ai_feedback($assign, $pending, $USER->id);
    
    // Update pending record status.
    $DB->set_field('local_assign_ai_rag_pending', 'status', assign_submission::STATUS_APPROVED, ['id' => $pendingid]);
    
    \core\notification::success(get_string('gradeapproved', 'local_assign_ai_rag'));
    redirect(new moodle_url('/local/assign_ai_rag/review.php', ['id' => $cmid]));
}

// Handle reject action - reset to initial for re-review.
if ($action === 'reject') {
    require_sesskey();
    
    $DB->set_field('local_assign_ai_rag_pending', 'status', assign_submission::STATUS_INITIAL, ['id' => $pendingid]);
    $DB->set_field('local_assign_ai_rag_pending', 'grade', null, ['id' => $pendingid]);
    $DB->set_field('local_assign_ai_rag_pending', 'message', null, ['id' => $pendingid]);
    $DB->set_field('local_assign_ai_rag_pending', 'citations', null, ['id' => $pendingid]);
    $DB->set_field('local_assign_ai_rag_pending', 'confidence', null, ['id' => $pendingid]);
    $DB->set_field('local_assign_ai_rag_pending', 'retrieved_docs', null, ['id' => $pendingid]);
    
    \core\notification::info(get_string('graderejected', 'local_assign_ai_rag'));
    redirect(new moodle_url('/local/assign_ai_rag/review.php', ['id' => $cmid]));
}

// Page setup.
$PAGE->set_url(new moodle_url('/local/assign_ai_rag/view_result.php', ['pendingid' => $pendingid]));
$PAGE->set_course($course);
$PAGE->set_context($context);
$PAGE->set_title(get_string('viewresult', 'local_assign_ai_rag'));
$PAGE->set_heading(format_string($course->fullname));
$PAGE->activityheader->disable();

// Get submission.
$submission = $assign->get_user_submission($student->id, false);

// Parse JSON data.
$citations = [];
if (!empty($pending->citations)) {
    $citations = json_decode($pending->citations, true) ?? [];
}

$retrievedDocs = [];
if (!empty($pending->retrieved_docs)) {
    $retrievedDocs = json_decode($pending->retrieved_docs, true) ?? [];
}

$criterionScores = [];
if (!empty($pending->rubric_response)) {
    $criterionScores = json_decode($pending->rubric_response, true) ?? [];
}

echo $OUTPUT->header();

// Back button.
$backurl = new moodle_url('/local/assign_ai_rag/review.php', ['id' => $cmid]);
echo '<div class="mb-3">';
echo '<a href="' . $backurl->out(false) . '" class="btn btn-secondary">&larr; ' . get_string('backtoreview', 'local_assign_ai_rag') . '</a>';
echo '</div>';

// Title.
echo '<h2>' . get_string('viewresult', 'local_assign_ai_rag') . '</h2>';
echo '<p class="text-muted">' . get_string('assignment', 'local_assign_ai_rag') . ': ' . s($assignment->name) . '</p>';

// Student info card.
echo '<div class="card mb-4">';
echo '<div class="card-header"><strong>' . get_string('studentinfo', 'local_assign_ai_rag') . '</strong></div>';
echo '<div class="card-body">';
echo '<div class="row">';
echo '<div class="col-md-6">';
echo '<p><strong>' . get_string('name', 'local_assign_ai_rag') . ':</strong> ' . fullname($student) . '</p>';
echo '<p><strong>' . get_string('email', 'local_assign_ai_rag') . ':</strong> ' . s($student->email) . '</p>';
echo '</div>';
echo '<div class="col-md-6">';
if ($submission) {
    echo '<p><strong>' . get_string('submissiontime', 'local_assign_ai_rag') . ':</strong> ' . userdate($submission->timemodified) . '</p>';
    echo '<p><strong>' . get_string('submissionstatus', 'local_assign_ai_rag') . ':</strong> ' . s($submission->status) . '</p>';
}
echo '</div>';
echo '</div>';

// Show submission files.
if ($submission) {
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
        echo '<p><strong>' . get_string('submittedfiles', 'local_assign_ai_rag') . ':</strong></p>';
        echo '<ul>';
        foreach ($files as $file) {
            $url = moodle_url::make_pluginfile_url(
                $file->get_contextid(),
                $file->get_component(),
                $file->get_filearea(),
                $file->get_itemid(),
                $file->get_filepath(),
                $file->get_filename()
            );
            echo '<li><a href="' . $url->out(false) . '" target="_blank">' . s($file->get_filename()) . '</a></li>';
        }
        echo '</ul>';
    }
    
    // Show online text if available.
    $onlinetext = $DB->get_record('assignsubmission_onlinetext', ['submission' => $submission->id]);
    if ($onlinetext && !empty($onlinetext->onlinetext)) {
        echo '<p><strong>' . get_string('onlinetext', 'local_assign_ai_rag') . ':</strong></p>';
        echo '<div class="border p-3 bg-light" style="max-height: 200px; overflow-y: auto;">';
        echo format_text($onlinetext->onlinetext, $onlinetext->onlineformat);
        echo '</div>';
    }
}
echo '</div>';
echo '</div>';

// AI Grading Result card.
echo '<div class="card mb-4">';
echo '<div class="card-header bg-primary text-white"><strong>🤖 ' . get_string('airesult', 'local_assign_ai_rag') . '</strong></div>';
echo '<div class="card-body">';

// Status badge.
$statusClass = 'bg-secondary';
$statusText = $pending->status;
switch ($pending->status) {
    case assign_submission::STATUS_INITIAL:
        $statusClass = 'bg-secondary';
        $statusText = get_string('initial', 'local_assign_ai_rag');
        break;
    case assign_submission::STATUS_PROCESSING:
        $statusClass = 'bg-warning';
        $statusText = get_string('processing', 'local_assign_ai_rag');
        break;
    case assign_submission::STATUS_PENDING:
        $statusClass = 'bg-info';
        $statusText = get_string('pending', 'local_assign_ai_rag');
        break;
    case assign_submission::STATUS_APPROVED:
        $statusClass = 'bg-success';
        $statusText = get_string('approved', 'local_assign_ai_rag');
        break;
}
echo '<p><strong>' . get_string('status', 'local_assign_ai_rag') . ':</strong> <span class="badge ' . $statusClass . '">' . $statusText . '</span></p>';

// Grade and confidence.
echo '<div class="row mb-3">';
echo '<div class="col-md-4">';
echo '<div class="card bg-light">';
echo '<div class="card-body text-center">';
echo '<h3 class="mb-0">' . ($pending->grade !== null ? format_float((float)$pending->grade, 2, true, true) : '-') . ' / ' . $assignment->grade . '</h3>';
echo '<small class="text-muted">' . get_string('aigrade', 'local_assign_ai_rag') . '</small>';
echo '</div></div></div>';

echo '<div class="col-md-4">';
echo '<div class="card bg-light">';
echo '<div class="card-body text-center">';
$confidencePercent = $pending->confidence !== null ? round($pending->confidence * 100) . '%' : '-';
$confidenceColor = 'text-secondary';
if ($pending->confidence !== null) {
    if ($pending->confidence >= 0.8) {
        $confidenceColor = 'text-success';
    } else if ($pending->confidence >= 0.5) {
        $confidenceColor = 'text-warning';
    } else {
        $confidenceColor = 'text-danger';
    }
}
echo '<h3 class="mb-0 ' . $confidenceColor . '">' . $confidencePercent . '</h3>';
echo '<small class="text-muted">' . get_string('confidence', 'local_assign_ai_rag') . '</small>';
echo '</div></div></div>';

echo '<div class="col-md-4">';
echo '<div class="card bg-light">';
echo '<div class="card-body text-center">';
echo '<h3 class="mb-0">' . count($retrievedDocs) . '</h3>';
echo '<small class="text-muted">' . get_string('retrieveddocs', 'local_assign_ai_rag') . '</small>';
echo '</div></div></div>';
echo '</div>';

// Feedback.
if (!empty($pending->message)) {
    echo '<div class="mb-4">';
    echo '<h5>' . get_string('feedback', 'local_assign_ai_rag') . '</h5>';
    echo '<div class="border p-3 bg-light">';
    echo nl2br(s($pending->message));
    echo '</div>';
    echo '</div>';
}

// Criterion scores.
if (!empty($criterionScores)) {
    echo '<div class="mb-4">';
    echo '<h5>' . get_string('criterionscores', 'local_assign_ai_rag') . '</h5>';
    echo '<table class="table table-bordered">';
    echo '<thead><tr><th>' . get_string('criterion', 'local_assign_ai_rag') . '</th><th>' . get_string('score', 'local_assign_ai_rag') . '</th></tr></thead>';
    echo '<tbody>';
    foreach ($criterionScores as $criterion => $score) {
        // AI responses store {score, feedback, evidence} per criterion; manual
        // rubric fillings store a list of {criterion, levels}. Render both.
        if (is_array($score) && array_key_exists('criterion', $score)) {
            $criterion = $score['criterion'];
            $level = $score['levels'][0] ?? [];
            $points = $level['points'] ?? '';
            $comment = $level['comment'] ?? '';
        } else if (is_array($score)) {
            $points = $score['score'] ?? '';
            $comment = $score['feedback'] ?? '';
        } else {
            $points = $score;
            $comment = '';
        }
        $pointstext = is_numeric($points) ? format_float((float)$points, 2, true, true) : s((string)$points);
        if ($comment !== '') {
            $pointstext .= '<br><small class="text-muted">' . s((string)$comment) . '</small>';
        }
        echo '<tr><td>' . s((string)$criterion) . '</td><td>' . $pointstext . '</td></tr>';
    }
    echo '</tbody></table>';
    echo '</div>';
}

// Citations.
if (!empty($citations)) {
    echo '<div class="mb-4">';
    echo '<h5>📚 ' . get_string('citations', 'local_assign_ai_rag') . '</h5>';
    echo '<ul class="list-group">';
    foreach ($citations as $citation) {
        echo '<li class="list-group-item">';
        if (is_array($citation)) {
            echo s($citation['text'] ?? $citation['content'] ?? json_encode($citation));
            if (!empty($citation['source'])) {
                echo '<br><small class="text-muted">Source: ' . s($citation['source']) . '</small>';
            }
        } else {
            echo s($citation);
        }
        echo '</li>';
    }
    echo '</ul>';
    echo '</div>';
}

// Retrieved documents.
if (!empty($retrievedDocs)) {
    echo '<div class="mb-4">';
    echo '<h5>📄 ' . get_string('retrieveddocs', 'local_assign_ai_rag') . '</h5>';
    echo '<div class="accordion" id="retrievedDocsAccordion">';
    $docIndex = 0;
    foreach ($retrievedDocs as $doc) {
        $docIndex++;
        $collapseId = 'doc' . $docIndex;
        $docText = is_array($doc) ? ($doc['text'] ?? $doc['content'] ?? json_encode($doc)) : $doc;
        $docSource = is_array($doc) ? ($doc['source'] ?? $doc['metadata']['source'] ?? 'Unknown') : 'Unknown';
        $docScore = is_array($doc) ? ($doc['score'] ?? $doc['relevance_score'] ?? '') : '';
        
        echo '<div class="accordion-item">';
        echo '<h2 class="accordion-header">';
        echo '<button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#' . $collapseId . '">';
        echo 'Document ' . $docIndex;
        if ($docScore) {
            echo ' <span class="badge bg-secondary ms-2">Score: ' . round((float)$docScore, 3) . '</span>';
        }
        echo '</button>';
        echo '</h2>';
        echo '<div id="' . $collapseId . '" class="accordion-collapse collapse" data-bs-parent="#retrievedDocsAccordion">';
        echo '<div class="accordion-body">';
        echo '<p><strong>Source:</strong> ' . s($docSource) . '</p>';
        echo '<p>' . nl2br(s(substr($docText, 0, 1000))) . (strlen($docText) > 1000 ? '...' : '') . '</p>';
        echo '</div></div></div>';
    }
    echo '</div>';
    echo '</div>';
}

echo '</div>';
echo '</div>';

// Action buttons.
if ($pending->status === assign_submission::STATUS_PENDING) {
    echo '<div class="card mb-4">';
    echo '<div class="card-header"><strong>' . get_string('actions', 'local_assign_ai_rag') . '</strong></div>';
    echo '<div class="card-body">';
    echo '<p>' . get_string('approvehint', 'local_assign_ai_rag') . '</p>';
    
    $approveurl = new moodle_url('/local/assign_ai_rag/view_result.php', [
        'pendingid' => $pendingid,
        'action' => 'approve',
        'sesskey' => sesskey(),
    ]);
    $rejecturl = new moodle_url('/local/assign_ai_rag/view_result.php', [
        'pendingid' => $pendingid,
        'action' => 'reject',
        'sesskey' => sesskey(),
    ]);
    
    echo '<a href="' . $approveurl->out(false) . '" class="btn btn-success btn-lg me-2">✓ ' . get_string('approve', 'local_assign_ai_rag') . '</a>';
    echo '<a href="' . $rejecturl->out(false) . '" class="btn btn-danger btn-lg">✗ ' . get_string('reject', 'local_assign_ai_rag') . '</a>';
    echo '</div>';
    echo '</div>';
} else if ($pending->status === assign_submission::STATUS_APPROVED) {
    echo '<div class="alert alert-success">';
    echo '<strong>✓</strong> ' . get_string('alreadyapproved', 'local_assign_ai_rag');
    echo '</div>';
} else if ($pending->status === assign_submission::STATUS_INITIAL) {
    echo '<div class="alert alert-info">';
    echo get_string('notreviewedyet', 'local_assign_ai_rag');
    echo '</div>';
}

echo $OUTPUT->footer();
