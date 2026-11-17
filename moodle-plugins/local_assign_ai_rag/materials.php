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
 * Materials management page for local_assign_ai_rag.
 * Upload course materials to the RAG knowledge base.
 *
 * @package     local_assign_ai_rag
 * @copyright   2025 Glenn H. K. M.
 * @license     https://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
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
require_once($CFG->dirroot . '/local/assign_ai_rag/locallib.php');
require_once($CFG->libdir . '/formslib.php');

// Course ID parameter.
$courseid = required_param('courseid', PARAM_INT);
$action = optional_param('action', '', PARAM_ALPHA);
$materialid = optional_param('materialid', 0, PARAM_INT);

// Get course.
$course = $DB->get_record('course', ['id' => $courseid], '*', MUST_EXIST);
$context = context_course::instance($courseid);

// Require login and capability.
require_login($course);
require_capability('local/assign_ai_rag:uploadmaterials', $context);

// Page setup.
$PAGE->set_url(new moodle_url('/local/assign_ai_rag/materials.php', ['courseid' => $courseid]));
$PAGE->set_context($context);
$PAGE->set_course($course);
$PAGE->set_title(get_string('materialsmanagement', 'local_assign_ai_rag'));
$PAGE->set_heading(format_string($course->fullname));

// Handle delete action.
if ($action === 'delete' && $materialid && confirm_sesskey()) {
    require_capability('local/assign_ai_rag:managematerials', $context);

    $material = $DB->get_record('local_assign_ai_rag_materials', ['id' => $materialid, 'courseid' => $courseid]);
    if ($material) {
        // Delete from database.
        $DB->delete_records('local_assign_ai_rag_materials', ['id' => $materialid]);

        // Optionally: Call RAG server to remove from vector store.
        // This would require implementing a delete endpoint on the RAG server.

        \core\notification::success('Material deleted successfully.');
    }
    redirect(new moodle_url('/local/assign_ai_rag/materials.php', ['courseid' => $courseid]));
}

// Handle clear all action.
if ($action === 'clearall' && confirm_sesskey()) {
    require_capability('local/assign_ai_rag:managematerials', $context);

    // Call RAG server to clear knowledge base.
    $serverurl = get_config('local_assign_ai_rag', 'server_url');
    if (empty($serverurl)) {
        \core\notification::error(get_string('serverunavailable', 'local_assign_ai_rag'));
        redirect(new moodle_url('/local/assign_ai_rag/materials.php', ['courseid' => $courseid]));
    }

    $headers = [
        'Accept: application/json',
        'Content-Type: application/x-www-form-urlencoded',
    ];
    $apikey = get_config('local_assign_ai_rag', 'api_key');
    if (!empty($apikey)) {
        $headers[] = 'Authorization: Bearer ' . $apikey;
    }

    $clearurl = rtrim($serverurl, '/') . '/course/materials/clear';
    $ch = curl_init($clearurl);
    curl_setopt_array($ch, [
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => http_build_query(['course_id' => (string) $courseid]),
        CURLOPT_HTTPHEADER => $headers,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_CONNECTTIMEOUT => 30,
        CURLOPT_TIMEOUT => 30,
    ]);
    $response = curl_exec($ch);
    $httpcode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $curlerror = curl_error($ch);
    curl_close($ch);

    $result = $response ? json_decode($response, true) : null;
    if ($curlerror || $httpcode !== 200 || empty($result['success'])) {
        \core\notification::error('Failed to clear materials from the RAG server.');
        redirect(new moodle_url('/local/assign_ai_rag/materials.php', ['courseid' => $courseid]));
    }

    $DB->delete_records('local_assign_ai_rag_materials', ['courseid' => $courseid]);
    \core\notification::success('All materials cleared.');
    redirect(new moodle_url('/local/assign_ai_rag/materials.php', ['courseid' => $courseid]));
}

// Upload form class.
class local_assign_ai_rag_upload_form extends moodleform
{
    public function definition()
    {
        $mform = $this->_form;

        $mform->addElement('hidden', 'courseid', $this->_customdata['courseid']);
        $mform->setType('courseid', PARAM_INT);

        $mform->addElement('filepicker', 'materialfile', get_string('uploadmaterials', 'local_assign_ai_rag'), null, [
            'maxbytes' => 50 * 1024 * 1024, // 50MB.
            'accepted_types' => ['.pdf', '.pptx', '.docx', '.txt'],
        ]);
        $mform->addRule('materialfile', null, 'required');

        $this->add_action_buttons(true, 'Upload');
    }
}

// Create form.
$form = new local_assign_ai_rag_upload_form(null, ['courseid' => $courseid]);

if ($form->is_cancelled()) {
    redirect(new moodle_url('/course/view.php', ['id' => $courseid]));
}
else if ($data = $form->get_data()) {
    // Handle file upload.
    $fs = get_file_storage();
    $draftitemid = file_get_submitted_draft_itemid('materialfile');

    // Get the file from the draft area.
    $usercontext = context_user::instance($USER->id);
    $draftfiles = $fs->get_area_files($usercontext->id, 'user', 'draft', $draftitemid, 'id DESC', false);

    if (!empty($draftfiles)) {
        $file = reset($draftfiles);
        $filename = $file->get_filename();
        $contenthash = $file->get_contenthash();
        $filepath = $file->copy_content_to_temp();

        // Get file extension.
        $ext = strtolower(pathinfo($filename, PATHINFO_EXTENSION));

        // Send to RAG server.
        $serverurl = get_config('local_assign_ai_rag', 'server_url');
        $timeout = get_config('local_assign_ai_rag', 'timeout') ?: 120;

        if (!empty($serverurl)) {
            $uploadurl = rtrim($serverurl, '/') . '/course/materials/upload';

            $ch = curl_init($uploadurl);

            // Prepare multipart form data.
            $postdata = [
                'file' => new CURLFile($filepath, $file->get_mimetype(), $filename),
                'course_id' => (string)$courseid,
                'course_name' => $course->fullname,
            ];

            curl_setopt($ch, CURLOPT_POST, true);
            curl_setopt($ch, CURLOPT_POSTFIELDS, $postdata);
            curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
            curl_setopt($ch, CURLOPT_TIMEOUT, $timeout);
            $headers = ['Accept: application/json'];
            $apikey = get_config('local_assign_ai_rag', 'api_key');
            if (!empty($apikey)) {
                $headers[] = 'Authorization: Bearer ' . $apikey;
            }
            curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);

            $response = curl_exec($ch);
            $httpcode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
            $curlerror = curl_error($ch);
            curl_close($ch);

            // Clean up temp file.
            @unlink($filepath);

            if (!$curlerror && $httpcode === 200) {
                $result = json_decode($response, true);
                if (empty($result['success'])) {
                    \core\notification::error('RAG server returned an invalid upload response.');
                    redirect(new moodle_url('/local/assign_ai_rag/materials.php', ['courseid' => $courseid]));
                }
                $chunkcount = $result['chunk_count'] ?? $result['chunks_created'] ?? 0;

                // Save to database.
                $record = (object)[
                    'courseid' => $courseid,
                    'filename' => $filename,
                    'contenthash' => $contenthash,
                    'filetype' => $ext,
                    'chunk_count' => $chunkcount,
                    'usermodified' => $USER->id,
                    'timecreated' => time(),
                ];
                $DB->insert_record('local_assign_ai_rag_materials', $record);

                \core\notification::success("File uploaded successfully. Created {$chunkcount} chunks in knowledge base.");
            }
            else {
                $detail = $curlerror ?: "HTTP Code: {$httpcode}";
                \core\notification::error("Failed to upload to RAG server. {$detail}");
            }
        }
        else {
            @unlink($filepath);
            \core\notification::error(get_string('serverunavailable', 'local_assign_ai_rag'));
        }
    }

    redirect(new moodle_url('/local/assign_ai_rag/materials.php', ['courseid' => $courseid]));
}

// Get existing materials.
$materials = $DB->get_records('local_assign_ai_rag_materials', ['courseid' => $courseid], 'timecreated DESC');

// Output page.
echo $OUTPUT->header();

echo '<div class="container-fluid">';

// Back button.
echo '<div class="mb-3">';
echo '<a href="' . (new moodle_url('/course/view.php', ['id' => $courseid]))->out(false) . '" class="btn btn-secondary">&larr; Back to Course</a>';
echo '</div>';

echo '<h2>' . get_string('materialsmanagement', 'local_assign_ai_rag') . '</h2>';
echo '<p class="text-muted">' . get_string('uploadmaterials_desc', 'local_assign_ai_rag') . '</p>';

// Server status.
$serverurl = get_config('local_assign_ai_rag', 'server_url');
if (empty($serverurl)) {
    echo '<div class="alert alert-warning">RAG server URL not configured. Go to Site Administration &gt; Plugins &gt; Local plugins &gt; RAG Assignment AI Grading to configure.</div>';
}
else {
    echo '<div class="alert alert-info">RAG Server: ' . s($serverurl) . '</div>';
}

// Upload form.
echo '<div class="card mb-4">';
echo '<div class="card-header">Upload New Material</div>';
echo '<div class="card-body">';
$form->display();
echo '</div>';
echo '</div>';

// Materials list.
echo '<div class="card">';
echo '<div class="card-header d-flex justify-content-between align-items-center">';
echo '<span>Uploaded Materials (' . count($materials) . ')</span>';
if (!empty($materials)) {
    $clearurl = new moodle_url('/local/assign_ai_rag/materials.php', [
        'courseid' => $courseid,
        'action' => 'clearall',
        'sesskey' => sesskey(),
    ]);
    echo '<a href="' . $clearurl->out(false) . '" class="btn btn-sm btn-danger" onclick="return confirm(\'' . get_string('clearmaterialsconfirm', 'local_assign_ai_rag') . '\');">Clear All</a>';
}
echo '</div>';
echo '<div class="card-body">';

if (empty($materials)) {
    echo '<p class="text-muted">' . get_string('nomaterials', 'local_assign_ai_rag') . '</p>';
}
else {
    echo '<table class="table table-sm">';
    echo '<thead><tr><th>Filename</th><th>Type</th><th>Chunks</th><th>Uploaded</th><th>Actions</th></tr></thead>';
    echo '<tbody>';
    foreach ($materials as $material) {
        $deleteurl = new moodle_url('/local/assign_ai_rag/materials.php', [
            'courseid' => $courseid,
            'action' => 'delete',
            'materialid' => $material->id,
            'sesskey' => sesskey(),
        ]);
        echo '<tr>';
        echo '<td>' . s($material->filename) . '</td>';
        echo '<td><span class="badge bg-secondary">' . strtoupper(s($material->filetype)) . '</span></td>';
        echo '<td>' . (int)$material->chunk_count . '</td>';
        echo '<td>' . userdate($material->timecreated) . '</td>';
        echo '<td><a href="' . $deleteurl->out(false) . '" class="btn btn-sm btn-outline-danger" onclick="return confirm(\'Delete this material?\');">Delete</a></td>';
        echo '</tr>';
    }
    echo '</tbody></table>';
}

echo '</div>';
echo '</div>';

echo '</div>';

echo $OUTPUT->footer();
