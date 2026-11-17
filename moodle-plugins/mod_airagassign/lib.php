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
 * Library of interface functions and constants for AI RAG Assignment module.
 *
 * @package    mod_airagassign
 * @copyright  2025 Glenn HKM
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

/**
 * Returns the features supported by this module.
 *
 * @param string $feature FEATURE_xx constant
 * @return mixed True if supported, null if unknown
 */
function airagassign_supports($feature) {
    switch ($feature) {
        case FEATURE_MOD_INTRO:
            return true;
        case FEATURE_SHOW_DESCRIPTION:
            return true;
        case FEATURE_GRADE_HAS_GRADE:
            return true;
        case FEATURE_BACKUP_MOODLE2:
            return true;
        case FEATURE_ADVANCED_GRADING:
            return true;
        case FEATURE_MOD_PURPOSE:
            return MOD_PURPOSE_ASSESSMENT;
        default:
            return null;
    }
}

/**
 * Add a new AI RAG Assignment instance.
 *
 * @param stdClass $data Form data
 * @param mod_airagassign_mod_form $mform The form
 * @return int The new instance id
 */
function airagassign_add_instance($data, $mform = null) {
    global $DB;

    // Decode dynamic table fields from JSON (these are invisible to moodleform::get_data()
    // but are passed via registered hidden fields serialised by JS on submit).
    if (!empty($data->criteria_json)) {
        $decoded = json_decode($data->criteria_json, true);
        if (is_array($decoded)) {
            $data->criterionname     = array_column($decoded, 'name');
            $data->criteriondesc     = array_column($decoded, 'desc');
            $data->criterionmaxscore = array_column($decoded, 'maxscore');
        }
    }
    if (!empty($data->questions_json)) {
        $decoded = json_decode($data->questions_json, true);
        if (is_array($decoded)) {
            $data->questions = $decoded;
        }
    }

    $data->timecreated = time();
    $data->timemodified = time();

    // Insert main record.
    $data->id = $DB->insert_record('airagassign', $data);

    // Save questions (quiz mode).
    if ($data->assignmode === 'quiz' && !empty($data->questions)) {
        foreach ($data->questions as $i => $qtext) {
            $qtext = trim($qtext);
            if ($qtext === '') {
                continue;
            }
            $question = new stdClass();
            $question->assignid = $data->id;
            $question->questiontext = $qtext;
            $question->sortorder = $i;
            $question->timecreated = time();
            $DB->insert_record('airagassign_questions', $question);
        }
    }

    // Save rubric criteria.
    if (($data->rubricmode ?? '') === 'custom' && !empty($data->criterionname)) {
        foreach ($data->criterionname as $i => $cname) {
            $cname = trim($cname);
            if ($cname === '') {
                continue;
            }
            $criterion = new stdClass();
            $criterion->assignid = $data->id;
            $criterion->name = $cname;
            $criterion->description = $data->criteriondesc[$i] ?? '';
            $criterion->maxscore = $data->criterionmaxscore[$i] ?? 100;
            $criterion->sortorder = $i;
            $DB->insert_record('airagassign_criteria', $criterion);
        }
    }

    // Save linked materials.
    if (!empty($data->materials)) {
        foreach ($data->materials as $materialid) {
            $link = new stdClass();
            $link->assignid = $data->id;
            $link->materialid = $materialid;
            $DB->insert_record('airagassign_materials', $link);
        }
    }

    // Save manual file if uploaded.
    $context = context_module::instance($data->coursemodule);
    if (isset($data->manualfile)) {
        file_save_draft_area_files(
            $data->manualfile,
            $context->id,
            'mod_airagassign',
            'manualfile',
            0,
            ['subdirs' => false, 'maxfiles' => 1]
        );
        airagassign_vectorize_manual_file($data->course, $context->id);
    }

    // Update gradebook.
    airagassign_grade_item_update($data);

    // Sync Moodle native rubric.
    airagassign_sync_moodle_rubric($data);

    return $data->id;
}

/**
 * Update an existing AI RAG Assignment instance.
 *
 * @param stdClass $data Form data
 * @param mod_airagassign_mod_form $mform The form
 * @return bool True on success
 */
function airagassign_update_instance($data, $mform = null) {
    global $DB;

    // Decode dynamic table fields from JSON.
    if (!empty($data->criteria_json)) {
        $decoded = json_decode($data->criteria_json, true);
        if (is_array($decoded)) {
            $data->criterionname     = array_column($decoded, 'name');
            $data->criteriondesc     = array_column($decoded, 'desc');
            $data->criterionmaxscore = array_column($decoded, 'maxscore');
        }
    }
    if (!empty($data->questions_json)) {
        $decoded = json_decode($data->questions_json, true);
        if (is_array($decoded)) {
            $data->questions = $decoded;
        }
    }

    $data->timemodified = time();
    $data->id = $data->instance;

    $DB->update_record('airagassign', $data);

    // Re-save questions.
    $DB->delete_records('airagassign_questions', ['assignid' => $data->id]);
    if ($data->assignmode === 'quiz' && !empty($data->questions)) {
        foreach ($data->questions as $i => $qtext) {
            $qtext = trim($qtext);
            if ($qtext === '') {
                continue;
            }
            $question = new stdClass();
            $question->assignid = $data->id;
            $question->questiontext = $qtext;
            $question->sortorder = $i;
            $question->timecreated = time();
            $DB->insert_record('airagassign_questions', $question);
        }
    }

    // Re-save rubric criteria.
    $DB->delete_records('airagassign_criteria', ['assignid' => $data->id]);
    if (($data->rubricmode ?? '') === 'custom' && !empty($data->criterionname)) {
        foreach ($data->criterionname as $i => $cname) {
            $cname = trim($cname);
            if ($cname === '') {
                continue;
            }
            $criterion = new stdClass();
            $criterion->assignid = $data->id;
            $criterion->name = $cname;
            $criterion->description = $data->criteriondesc[$i] ?? '';
            $criterion->maxscore = $data->criterionmaxscore[$i] ?? 100;
            $criterion->sortorder = $i;
            $DB->insert_record('airagassign_criteria', $criterion);
        }
    }

    // Re-save linked materials.
    $DB->delete_records('airagassign_materials', ['assignid' => $data->id]);
    if (!empty($data->materials)) {
        foreach ($data->materials as $materialid) {
            $link = new stdClass();
            $link->assignid = $data->id;
            $link->materialid = $materialid;
            $DB->insert_record('airagassign_materials', $link);
        }
    }

    // Re-save manual file.
    $context = context_module::instance($data->coursemodule);
    if (isset($data->manualfile)) {
        $oldfiles = airagassign_get_uploaded_files($context->id);
        
        file_save_draft_area_files(
            $data->manualfile,
            $context->id,
            'mod_airagassign',
            'manualfile',
            0,
            ['subdirs' => false, 'maxfiles' => 1]
        );
        
        $newfiles = airagassign_get_uploaded_files($context->id);
        
        // If file changed/removed, delete old file's vectors.
        foreach ($oldfiles as $oldfile) {
            $oldname = $oldfile->get_filename();
            $still_exists = false;
            foreach ($newfiles as $newfile) {
                if ($newfile->get_filename() === $oldname) {
                    $still_exists = true;
                    break;
                }
            }
            if (!$still_exists) {
                airagassign_delete_file_vectors($data->course, $oldname);
            }
        }
        
        // Vectorize if new/changed.
        foreach ($newfiles as $newfile) {
            $newname = $newfile->get_filename();
            $was_present = false;
            foreach ($oldfiles as $oldfile) {
                if ($oldfile->get_filename() === $newname) {
                    $was_present = true;
                    break;
                }
            }
            if (!$was_present) {
                airagassign_vectorize_manual_file($data->course, $context->id);
            }
        }
    }

    // Update gradebook.
    airagassign_grade_item_update($data);

    // Sync Moodle native rubric.
    airagassign_sync_moodle_rubric($data);

    return true;
}

/**
 * Delete an AI RAG Assignment instance.
 *
 * @param int $id Instance ID
 * @return bool True on success
 */
function airagassign_delete_instance($id) {
    global $DB;

    $assign = $DB->get_record('airagassign', ['id' => $id]);
    if (!$assign) {
        return false;
    }

    // Clean up manual files and their vector store records first.
    $cm = get_coursemodule_from_instance('airagassign', $id);
    if ($cm) {
        $context = context_module::instance($cm->id);
        $files = airagassign_get_uploaded_files($context->id);
        foreach ($files as $file) {
            airagassign_delete_file_vectors($assign->course, $file->get_filename());
        }
    }

    // Delete answers for all submissions.
    $submissions = $DB->get_records('airagassign_submissions', ['assignid' => $id], '', 'id');
    foreach ($submissions as $sub) {
        $DB->delete_records('airagassign_answers', ['submissionid' => $sub->id]);
    }

    $DB->delete_records('airagassign_submissions', ['assignid' => $id]);
    $DB->delete_records('airagassign_questions', ['assignid' => $id]);
    $DB->delete_records('airagassign_criteria', ['assignid' => $id]);
    $DB->delete_records('airagassign_materials', ['assignid' => $id]);
    $DB->delete_records('airagassign', ['id' => $id]);

    // Remove grade item.
    airagassign_grade_item_delete($assign);

    return true;
}

/**
 * Create/update grade item in gradebook.
 *
 * @param stdClass $assign The assignment instance
 * @param mixed $grades Optional grade data
 * @return int
 */
function airagassign_grade_item_update($assign, $grades = null) {
    global $CFG;
    require_once($CFG->libdir . '/gradelib.php');

    $params = [
        'itemname' => $assign->name,
        'gradetype' => GRADE_TYPE_VALUE,
        'grademax' => $assign->maximumgrade,
        'grademin' => 0,
    ];

    if ($grades === 'reset') {
        $params['reset'] = true;
        $grades = null;
    }

    return grade_update('mod/airagassign', $assign->course, 'mod', 'airagassign', $assign->id, 0, $grades, $params);
}

/**
 * Delete grade item from gradebook.
 *
 * @param stdClass $assign The assignment instance
 * @return int
 */
function airagassign_grade_item_delete($assign) {
    global $CFG;
    require_once($CFG->libdir . '/gradelib.php');

    return grade_update('mod/airagassign', $assign->course, 'mod', 'airagassign', $assign->id, 0, null, ['deleted' => 1]);
}

/**
 * Update grades in gradebook.
 *
 * @param stdClass $assign The assignment instance
 * @param int $userid User ID (0 for all)
 * @param bool $nullifnone Set to null if no grade
 */
function airagassign_update_grades($assign, $userid = 0, $nullifnone = true) {
    global $CFG, $DB;
    require_once($CFG->libdir . '/gradelib.php');

    if ($userid) {
        $submissions = $DB->get_records('airagassign_submissions', [
            'assignid' => $assign->id,
            'userid' => $userid,
            'status' => 'graded',
        ]);
    } else {
        $submissions = $DB->get_records('airagassign_submissions', [
            'assignid' => $assign->id,
            'status' => 'graded',
        ]);
    }

    $grades = [];
    foreach ($submissions as $sub) {
        $grade = new stdClass();
        $grade->userid = $sub->userid;
        $grade->rawgrade = $sub->grade;
        $grade->dategraded = $sub->timegraded;
        $grade->datesubmitted = $sub->timecreated;
        $grades[$sub->userid] = $grade;
    }

    if (empty($grades) && $nullifnone) {
        if ($userid) {
            $grade = new stdClass();
            $grade->userid = $userid;
            $grade->rawgrade = null;
            $grades[$userid] = $grade;
        }
    }

    airagassign_grade_item_update($assign, $grades);
}

/**
 * Build the rubric dictionary from the criteria for API call.
 *
 * @param int $assignid Assignment ID
 * @return array Rubric dictionary
 */
function airagassign_build_rubric($assignid) {
    global $DB;

    $assign = $DB->get_record('airagassign', ['id' => $assignid]);
    if (!$assign) {
        return [];
    }

    $rubricmode = $assign->rubricmode ?? 'custom';
    if ($rubricmode === 'moodle') {
        return airagassign_build_moodle_rubric($assign);
    }

    if ($rubricmode === 'simple') {
        return [];
    }

    $criteria = $DB->get_records('airagassign_criteria', ['assignid' => $assignid], 'sortorder ASC');
    $rubric = [];
    foreach ($criteria as $c) {
        $rubric[$c->name] = [
            'description' => $c->description,
            'max_score' => (float)$c->maxscore,
        ];
    }
    return $rubric;
}

/**
 * Build the rubric dictionary from Moodle's native advanced grading rubric.
 *
 * @param stdClass $assign The assignment instance.
 * @return array Rubric dictionary
 */
function airagassign_build_moodle_rubric($assign) {
    global $CFG;
    require_once($CFG->dirroot . '/grade/grading/lib.php');

    $cm = get_coursemodule_from_instance('airagassign', $assign->id);
    if (!$cm) {
        return [];
    }

    $context = context_module::instance($cm->id);
    $gradingmanager = get_grading_manager($context, 'mod_airagassign', 'submissions');
    if (!$gradingmanager) {
        return [];
    }

    $controller = $gradingmanager->get_active_controller();
    if (!$controller || $controller->get_method() !== 'rubric') {
        return [];
    }

    $definition = $controller->get_definition(true);
    if (empty($definition) || empty($definition->rubric_criteria)) {
        return [];
    }

    $rubric = [];
    foreach ($definition->rubric_criteria as $criterionid => $criterion) {
        $name = trim($criterion['description']);
        if ($name === '') {
            $name = "Criterion " . $criterionid;
        }

        $maxscore = 0.0;
        $leveldescriptions = [];
        if (!empty($criterion['levels'])) {
            foreach ($criterion['levels'] as $level) {
                $score = (float)$level['score'];
                if ($score > $maxscore) {
                    $maxscore = $score;
                }
                $leveldescriptions[] = sprintf("- %s (%s pts)", trim($level['definition']), $score);
            }
        }

        $description = implode("\n", $leveldescriptions);

        $rubric[$name] = [
            'description' => $description,
            'max_score' => $maxscore,
        ];
    }

    return $rubric;
}

/**
 * Get the list of uploaded manual files for an assignment instance.
 *
 * @param int $contextid The context ID
 * @return array List of stored_file objects
 */
function airagassign_get_uploaded_files($contextid) {
    $fs = get_file_storage();
    $files = $fs->get_area_files($contextid, 'mod_airagassign', 'manualfile', 0, 'filename', false);
    return $files;
}

/**
 * Vectorize the manual reference/answer key file on the RAG server.
 *
 * @param int $courseid Course ID
 * @param int $contextid Context ID
 * @return array Result status
 */
function airagassign_vectorize_manual_file($courseid, $contextid) {
    $serverurl = get_config('mod_airagassign', 'serverurl');
    if (empty($serverurl)) {
        $serverurl = 'http://127.0.0.1:8000';
    }

    $files = airagassign_get_uploaded_files($contextid);
    if (empty($files)) {
        return ['success' => false, 'error' => 'No files found to vectorize'];
    }

    $errors = [];
    foreach ($files as $file) {
        $filename = $file->get_filename();
        
        // Create a temp file for curl upload.
        $tempdir = make_temp_directory('airagassign');
        $tempfile = $tempdir . '/' . $filename;
        $file->copy_content_to($tempfile);

        // Send to RAG server.
        $result = airagassign_send_file_to_rag($serverurl, $tempfile, $filename, $courseid);

        // Clean up temp file.
        @unlink($tempfile);

        if (!$result['success']) {
            $errors[] = $filename . ': ' . ($result['error'] ?? 'Unknown error');
        }
    }

    if (!empty($errors)) {
        return ['success' => false, 'error' => implode("\n", $errors)];
    }
    return ['success' => true];
}

/**
 * Build HTTP headers for RAG API requests, appending Bearer auth when configured.
 *
 * @param array $headers Base HTTP headers
 * @return array Complete HTTP headers
 */
function airagassign_build_api_headers(array $headers = []): array {
    $apikey = trim((string)get_config('mod_airagassign', 'apikey'));
    if ($apikey !== '') {
        $headers[] = 'Authorization: Bearer ' . $apikey;
    }
    return $headers;
}

/**
 * Send a manual file to the RAG server for vectorization.
 *
 * @param string $serverurl RAG server base URL
 * @param string $filepath Local file path
 * @param string $filename Original filename
 * @param int $courseid Course ID
 * @return array Result array
 */
function airagassign_send_file_to_rag($serverurl, $filepath, $filename, $courseid) {
    $url = rtrim($serverurl, '/') . '/course/materials/upload';

    $ch = curl_init();
    curl_setopt_array($ch, [
        CURLOPT_URL => $url,
        CURLOPT_POST => true,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT => 300,
        CURLOPT_CONNECTTIMEOUT => 30,
        CURLOPT_HTTPHEADER => airagassign_build_api_headers(['Accept: application/json']),
        CURLOPT_POSTFIELDS => [
            'file' => new CURLFile($filepath, '', $filename),
            'course_id' => (string)$courseid,
            'course_name' => '',
        ],
    ]);

    $response = curl_exec($ch);
    $httpcode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $curlerror = curl_error($ch);
    curl_close($ch);

    if ($curlerror) {
        return ['success' => false, 'error' => 'Connection error: ' . $curlerror];
    }

    if ($httpcode !== 200) {
        return ['success' => false, 'error' => "HTTP $httpcode: " . substr($response, 0, 500)];
    }

    $data = json_decode($response, true);
    if (!$data) {
        return ['success' => false, 'error' => 'Invalid JSON response'];
    }

    if (empty($data['success'])) {
        return ['success' => false, 'error' => $data['message'] ?? $data['detail'] ?? 'Server error'];
    }

    return [
        'success' => true,
        'chunks_created' => $data['chunk_count'] ?? $data['chunks_created'] ?? 0,
        'documents_loaded' => $data['documents_loaded'] ?? 1,
        'total_in_db' => $data['total_documents_in_db'] ?? 0,
    ];
}

/**
 * Delete a file's vectors from the RAG server.
 *
 * @param int $courseid Course ID
 * @param string $filename File name
 * @return bool True on success
 */
function airagassign_delete_file_vectors($courseid, $filename) {
    $serverurl = get_config('mod_airagassign', 'serverurl');
    if (empty($serverurl)) {
        $serverurl = 'http://127.0.0.1:8000';
    }

    $ch = curl_init();
    curl_setopt_array($ch, [
        CURLOPT_URL            => rtrim($serverurl, '/') . '/course/materials/file',
        CURLOPT_CUSTOMREQUEST  => 'DELETE',
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 30,
        CURLOPT_POSTFIELDS     => http_build_query([
            'course_id' => (string)$courseid,
            'filename'  => $filename,
        ]),
        CURLOPT_HTTPHEADER     => airagassign_build_api_headers(['Content-Type: application/x-www-form-urlencoded']),
    ]);
    $response  = curl_exec($ch);
    $httpcode  = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $curlerror = curl_error($ch);
    curl_close($ch);

    if ($curlerror || $httpcode !== 200) {
        debugging(
            "airagassign_delete_file_vectors: failed to delete vectors for '$filename' " .
            "(course $courseid). HTTP $httpcode — $curlerror",
            DEBUG_DEVELOPER
        );
        return false;
    }

    return true;
}

/**
 * Collect linked airagmaterial filenames and manual reference filenames for scoped RAG retrieval.
 *
 * @param int $assignid Assignment instance ID
 * @param int $contextid Module context ID
 * @return array List of unique material basenames
 */
function airagassign_get_linked_material_filenames(int $assignid, int $contextid): array {
    global $DB;

    $filenames = [];
    // {airagmaterial_files} tracks per-file vectorization via `vectorized` (0/1),
    // while `vectorize_status` lives on {airagmaterial}.
    $sql = "SELECT DISTINCT af.filename
              FROM {airagassign_materials} aam
              JOIN {airagmaterial} am ON am.id = aam.materialid
              JOIN {airagmaterial_files} af ON af.materialid = am.id
             WHERE aam.assignid = :assignid
               AND am.vectorize_status = 'completed'
               AND af.vectorized = 1";
    $records = $DB->get_records_sql($sql, ['assignid' => $assignid]);
    foreach ($records as $record) {
        $name = basename(trim((string)($record->filename ?? '')));
        if ($name !== '' && $name !== '.') {
            $filenames[$name] = true;
        }
    }

    foreach (airagassign_get_uploaded_files($contextid) as $file) {
        $name = basename(trim((string)$file->get_filename()));
        if ($name !== '' && $name !== '.') {
            $filenames[$name] = true;
        }
    }

    return array_keys($filenames);
}

/**
 * Grade a single submission using the RAG API.
 *
 * @param stdClass $assign The assignment record
 * @param stdClass $submission The submission record
 * @param context_module $context The module context
 * @return array Result with success status
 */
function airagassign_grade_submission($assign, $submission, $context) {
    global $DB;

    $serverurl = get_config('mod_airagassign', 'serverurl');
    if (empty($serverurl)) {
        $serverurl = 'http://127.0.0.1:8000';
    }

    $rubric = airagassign_build_rubric($assign->id);
    if (($assign->rubricmode ?? '') === 'moodle' && empty($rubric)) {
        return [
            'success' => false,
            'error' => get_string('moodlerubric_not_configured', 'airagassign'),
        ];
    }

    $sourcefilter = airagassign_get_linked_material_filenames((int)$assign->id, (int)$context->id);

    if ($assign->assignmode === 'quiz') {
        return airagassign_grade_quiz_submission($assign, $submission, $rubric, $serverurl, $sourcefilter);
    } else {
        return airagassign_grade_essay_submission($assign, $submission, $rubric, $serverurl, $sourcefilter);
    }
}

/**
 * Persist an AI grading failure for teacher review and retry.
 *
 * @param int $submissionid Submission ID
 * @param string $error Error message
 * @param string $requestid API request ID, when available
 */
function airagassign_record_grading_failure($submissionid, $error, $requestid = '') {
    global $DB;

    $cleanerror = trim(strip_tags((string)$error));
    if ($cleanerror === '') {
        $cleanerror = 'Unknown grading error';
    }
    $cleanerror = core_text::substr($cleanerror, 0, 4000);

    $record = (object)[
        'id' => (int)$submissionid,
        'status' => 'grading_failed',
        'grading_error' => $cleanerror,
        'grading_requestid' => core_text::substr(trim((string)$requestid), 0, 64),
        'grading_started_at' => 0,
    ];
    $DB->update_record('airagassign_submissions', $record);
}

/**
 * Grade a quiz-mode submission (per-question grading).
 *
 * @param stdClass $assign Assignment record
 * @param stdClass $submission Submission record
 * @param array $rubric Rubric dictionary
 * @param string $serverurl RAG server URL
 * @param array $sourcefilter Optional list of source filenames for scoped retrieval
 * @return array Result
 */
function airagassign_grade_quiz_submission($assign, $submission, $rubric, $serverurl, array $sourcefilter = []) {
    global $DB;

    $questions = $DB->get_records('airagassign_questions', ['assignid' => $assign->id], 'sortorder ASC');
    $answers = $DB->get_records('airagassign_answers', ['submissionid' => $submission->id]);

    // Index answers by question ID.
    $answermap = [];
    foreach ($answers as $a) {
        $answermap[$a->questionid] = $a;
    }

    $numquestions = count($questions);
    if ($numquestions == 0) {
        return ['success' => false, 'error' => 'No questions defined'];
    }

    $gradeperquestion = (float)$assign->maximumgrade / $numquestions;
    $totalscore = 0;
    $allfeedback = [];
    $allerrors = [];
    $failedrequestid = '';

    foreach ($questions as $question) {
        $answer = $answermap[$question->id] ?? null;
        if (!$answer) {
            continue;
        }

        // Call RAG API for this question.
        $payload = [
            'course_id' => $assign->course,
            'question' => $question->questiontext,
            'essay' => $answer->answertext,
            'rubric' => $rubric,
            'maximum_grade' => $gradeperquestion,
            'assignment_id' => $assign->id,
        ];
        if (!empty($sourcefilter)) {
            $payload['source_filter'] = array_values($sourcefilter);
        }
        $result = airagassign_call_rag_api($serverurl, $payload);

        if ($result['success']) {
            $qscore    = (float)($result['data']['score']    ?? 0);
            $qfeedback = $result['data']['feedback'] ?? '';

            // Store AI suggestion in separate columns — final score/feedback
            // is only written when the teacher confirms via grade_review.php.
            $answer->ai_score    = $qscore;
            $answer->ai_feedback = $qfeedback;
            $answer->ai_response = json_encode($result['data']);
            $DB->update_record('airagassign_answers', $answer);

            $totalscore += $qscore;
            $allfeedback[] = "Q" . ($question->sortorder + 1) . ": " . $qfeedback;
        } else {
            $allerrors[] = "Q" . ($question->sortorder + 1) . ": " . ($result['error'] ?? 'Unknown error');
            $failedrequestid = $result['requestid'] ?? $failedrequestid;
        }
    }

    if (!empty($allerrors)) {
        return [
            'success' => false,
            'error' => implode('; ', $allerrors),
            'requestid' => $failedrequestid,
        ];
    }

    // Store AI suggestion — teacher must confirm via grade_review.php.
    $submission->ai_grade    = round($totalscore, 2);
    $submission->ai_feedback = implode("\n\n", $allfeedback);
    $submission->status      = 'ai_suggested';
    $submission->grading_error = null;
    $submission->grading_requestid = null;
    $submission->grading_started_at = 0;
    $submission->timegraded  = time();
    $DB->update_record('airagassign_submissions', $submission);

    return [
        'success'  => true,
        'ai_grade' => $submission->ai_grade,
        'feedback' => $submission->ai_feedback,
        'errors'   => $allerrors,
    ];
}

/**
 * Grade an essay-mode submission (single grading).
 *
 * @param stdClass $assign Assignment record
 * @param stdClass $submission Submission record
 * @param array $rubric Rubric dictionary
 * @param string $serverurl RAG server URL
 * @param array $sourcefilter Optional list of source filenames for scoped retrieval
 * @return array Result
 */
function airagassign_grade_essay_submission($assign, $submission, $rubric, $serverurl, array $sourcefilter = []) {
    global $DB;

    // Get the essay answer.
    $answer = $DB->get_record('airagassign_answers', ['submissionid' => $submission->id]);
    if (!$answer) {
        return ['success' => false, 'error' => 'No essay answer found'];
    }

    $payload = [
        'course_id' => $assign->course,
        'question' => $assign->essayprompt,
        'essay' => $answer->answertext,
        'rubric' => $rubric,
        'maximum_grade' => (float)$assign->maximumgrade,
        'assignment_id' => $assign->id,
    ];
    if (!empty($sourcefilter)) {
        $payload['source_filter'] = array_values($sourcefilter);
    }
    $result = airagassign_call_rag_api($serverurl, $payload);

    if (!$result['success']) {
        return $result;
    }

    $score      = (float)($result['data']['score']      ?? 0);
    $feedback   = $result['data']['feedback']   ?? '';
    $confidence = (float)($result['data']['confidence'] ?? 0);

    // Store AI suggestion in separate columns — score/feedback remain empty
    // until the teacher confirms the grade in grade_review.php.
    $answer->ai_score    = $score;
    $answer->ai_feedback = $feedback;
    $answer->ai_response = json_encode($result['data']);
    $DB->update_record('airagassign_answers', $answer);

    // Update submission with AI suggestion (NOT final grade).
    $submission->ai_grade    = round($score, 2);
    $submission->ai_feedback = $feedback;
    $submission->ai_response = json_encode($result['data']);
    $submission->confidence  = $confidence;
    $submission->status      = 'ai_suggested';
    $submission->grading_error = null;
    $submission->grading_requestid = null;
    $submission->grading_started_at = 0;
    $submission->timegraded  = time();
    $DB->update_record('airagassign_submissions', $submission);

    return [
        'success'  => true,
        'ai_grade' => $submission->ai_grade,
        'feedback' => $feedback,
    ];
}

/**
 * Call the RAG API for grading.
 *
 * @param string $serverurl RAG server URL
 * @param array $payload Request payload
 * @return array Result with success and data/error
 */
function airagassign_call_rag_api($serverurl, $payload) {
    $url = rtrim($serverurl, '/') . '/assign/answer';
    $requestid = bin2hex(random_bytes(16));
    $responseheaders = [];

    // FastAPI expects rubric to be a JSON object. In simple grading mode there
    // is no rubric, and PHP would encode an empty array as [] which triggers a
    // 422 validation error before the request reaches the grading logic.
    if (!isset($payload['rubric']) || (is_array($payload['rubric']) && empty($payload['rubric']))) {
        $payload['rubric'] = new stdClass();
    }

    $jsonpayload = json_encode($payload);

    $ch = curl_init();
    curl_setopt_array($ch, [
        CURLOPT_URL => $url,
        CURLOPT_POST => true,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT => 120,
        CURLOPT_CONNECTTIMEOUT => 30,
        CURLOPT_HTTPHEADER => airagassign_build_api_headers([
            'Content-Type: application/json',
            'Accept: application/json',
            'X-Request-ID: ' . $requestid,
        ]),
        CURLOPT_HEADERFUNCTION => function($curl, $header) use (&$responseheaders) {
            $length = strlen($header);
            $parts = explode(':', $header, 2);
            if (count($parts) === 2) {
                $responseheaders[strtolower(trim($parts[0]))] = trim($parts[1]);
            }
            return $length;
        },
        CURLOPT_POSTFIELDS => $jsonpayload,
    ]);

    $response = curl_exec($ch);
    $httpcode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $curlerror = curl_error($ch);
    curl_close($ch);

    if (!empty($responseheaders['x-request-id'])) {
        $requestid = core_text::substr($responseheaders['x-request-id'], 0, 64);
    }

    if ($curlerror) {
        return ['success' => false, 'error' => 'Connection error: ' . $curlerror, 'requestid' => $requestid];
    }

    if ($httpcode !== 200) {
        $detail = '';
        $decoded = json_decode($response, true);
        if ($decoded && isset($decoded['detail'])) {
            $detail = is_string($decoded['detail']) ? $decoded['detail'] : json_encode($decoded['detail']);
        } else {
            $detail = substr($response, 0, 500);
        }
        return ['success' => false, 'error' => "HTTP $httpcode: $detail", 'requestid' => $requestid];
    }

    $data = json_decode($response, true);
    if (!$data) {
        return ['success' => false, 'error' => 'Invalid JSON response from server', 'requestid' => $requestid];
    }

    if (isset($data['success']) && !$data['success']) {
        return [
            'success' => false,
            'error' => $data['error'] ?? $data['message'] ?? 'Server returned failure',
            'requestid' => $requestid,
        ];
    }

    return ['success' => true, 'data' => $data, 'requestid' => $requestid];
}

/**
 * Return view actions for participation report.
 *
 * @return array
 */
function airagassign_get_view_actions() {
    return ['view', 'view all'];
}

/**
 * Return post actions for participation report.
 *
 * @return array
 */
function airagassign_get_post_actions() {
    return ['submit', 'grade'];
}

/**
 * Serves the files from this plugin.
 *
 * @param stdClass $course
 * @param stdClass $cm
 * @param stdClass $context
 * @param string $filearea
 * @param array $args
 * @param bool $forcedownload
 * @param array $options
 * @return bool
 */
function airagassign_pluginfile($course, $cm, $context, $filearea, $args, $forcedownload, array $options = []) {
    if ($context->contextlevel != CONTEXT_MODULE) {
        return false;
    }

    require_course_login($course, true, $cm);

    if ($filearea !== 'manualfile') {
        return false;
    }

    $itemid = array_shift($args);
    $filename = array_pop($args);
    $filepath = $args ? '/' . implode('/', $args) . '/' : '/';

    $fs = get_file_storage();
    $file = $fs->get_file($context->id, 'mod_airagassign', $filearea, $itemid, $filepath, $filename);

    if (!$file) {
        return false;
    }

    send_stored_file($file, 0, 0, $forcedownload, $options);
}

/**
 * Synchronize the selected Moodle advanced grading method.
 *
 * This only enables/disables Moodle native Rubric for the grade item. It must
 * not create or overwrite rubric definitions, because those criteria should be
 * configured by the teacher through Moodle's Advanced grading UI.
 *
 * @param stdClass $data Form data or assignment instance data
 */
function airagassign_sync_moodle_rubric($data) {
    global $CFG;

    $assignid = $data->id;
    // Check rubricmode. If not 'moodle', do not sync or disable rubric method.
    $rubricmode = $data->rubricmode ?? '';
    
    // Get course module and context.
    $cm = get_coursemodule_from_instance('airagassign', $assignid, 0, false, IGNORE_MISSING);
    if (!$cm) {
        return;
    }
    $context = context_module::instance($cm->id);

    require_once($CFG->dirroot . '/grade/grading/lib.php');
    $gradingmanager = get_grading_manager($context, 'mod_airagassign', 'submissions');
    
    if ($rubricmode !== 'moodle') {
        // If not Moodle Native Rubric, make sure native advanced grading is disabled (simple direct grading).
        $activemethod = $gradingmanager->get_active_method();
        if (!empty($activemethod)) {
            $gradingmanager->set_active_method('');
        }
        return;
    }

    // Enable Moodle native Rubric for this grade item, then let the teacher
    // define the actual rubric through Moodle's Advanced grading UI. Do not
    // auto-create or overwrite criteria here; the API payload must reflect the
    // rubric configured by the teacher, not a generated fallback.
    $gradingmanager->set_active_method('rubric');
}
