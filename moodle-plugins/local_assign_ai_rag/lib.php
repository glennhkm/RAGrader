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
 * Library functions for local_assign_ai_rag.
 *
 * @package     local_assign_ai_rag
 * @copyright   2025 Glenn H. K. M.
 * @license     https://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

global $CFG;
require_once($CFG->dirroot . '/local/assign_ai_rag/locallib.php');

/**
 * Extends assignment navigation to display the "AI Review with RAG" button.
 *
 * @param settings_navigation $nav     The settings navigation object.
 * @param context             $context The current context.
 * @package local_assign_ai_rag
 */
function local_assign_ai_rag_extend_settings_navigation(settings_navigation $nav, context $context) {
    global $PAGE, $DB;

    // Verify that we are in a module (activity) context.
    if ($context->contextlevel != CONTEXT_MODULE) {
        return;
    }

    // Verify that it is an assignment.
    if ($PAGE->cm->modname !== 'assign') {
        return;
    }

    // Find the module settings node.
    $modulesettings = $nav->find('modulesettings', navigation_node::TYPE_SETTING);

    if ($modulesettings) {
        $url = new moodle_url('/local/assign_ai_rag/review.php', ['id' => $PAGE->cm->id]);

        $modulesettings->add(
            get_string('reviewwithai', 'local_assign_ai_rag'),
            $url,
            navigation_node::TYPE_SETTING,
            null,
            'assign_ai_rag_config',
            new pix_icon('i/settings', '')
        );

        // Add materials management link at course level.
        $course = $PAGE->course;
        if ($course) {
            $materialsurl = new moodle_url('/local/assign_ai_rag/materials.php', ['courseid' => $course->id]);
            $modulesettings->add(
                get_string('uploadmaterials', 'local_assign_ai_rag'),
                $materialsurl,
                navigation_node::TYPE_SETTING,
                null,
                'assign_ai_rag_materials',
                new pix_icon('i/files', '')
            );
        }
    }
}

/**
 * Adds AI configuration elements to the module form.
 *
 * @param moodleform_mod $formwrapper
 * @param MoodleQuickForm $mform
 * @return void
 */
function local_assign_ai_rag_coursemodule_standard_elements($formwrapper, $mform) {
    global $USER, $DB;

    if ($formwrapper->get_current()->modulename !== 'assign') {
        return;
    }

    $courseid = $formwrapper->get_course()->id ?? $formwrapper->get_current()->course ?? null;
    if (!$courseid) {
        return;
    }

    $context = context_course::instance($courseid);
    if (!has_capability('moodle/course:manageactivities', $context, $USER)) {
        return;
    }

    $assignid = $formwrapper->get_current()->instance ?? 0;
    $config = $assignid ? local_assign_ai_rag_get_assignment_config($assignid) : null;
    $default = $config->autograde ?? 0;
    $graderdefault = $config->graderid ?? null;
    $usematerials = $config->use_course_materials ?? 1;

    $mform->addElement('header', 'local_assign_ai_rag_header', get_string('aiconfigheader', 'local_assign_ai_rag'));
    
    // Auto-grade option.
    $mform->addElement(
        'select',
        'local_assign_ai_rag_autograde',
        get_string('autograde', 'local_assign_ai_rag'),
        [0 => get_string('no'), 1 => get_string('yes')]
    );
    $mform->addHelpButton('local_assign_ai_rag_autograde', 'autograde', 'local_assign_ai_rag');
    $mform->setDefault('local_assign_ai_rag_autograde', $default);

    // Use course materials (RAG) option.
    $mform->addElement(
        'select',
        'local_assign_ai_rag_usematerials',
        get_string('usecoursematerials', 'local_assign_ai_rag'),
        [0 => get_string('no'), 1 => get_string('yes')]
    );
    $mform->addHelpButton('local_assign_ai_rag_usematerials', 'usecoursematerials', 'local_assign_ai_rag');
    $mform->setDefault('local_assign_ai_rag_usematerials', $usematerials);

    // Grader selection.
    $eligibleusers = get_enrolled_users($context, 'mod/assign:grade');
    $options = [];
    foreach ($eligibleusers as $user) {
        $options[$user->id] = fullname($user);
    }

    if ($graderdefault && !isset($options[$graderdefault])) {
        $graderuser = $DB->get_record(
            'user',
            ['id' => $graderdefault],
            'id, firstname, lastname, firstnamephonetic, lastnamephonetic, middlename, alternatename'
        );
        if ($graderuser) {
            $options[$graderuser->id] = fullname($graderuser);
        }
    }

    if (!empty($options)) {
        \core_collator::asort($options);
    }

    $mform->addElement(
        'autocomplete',
        'local_assign_ai_rag_grader',
        get_string('autogradegrader', 'local_assign_ai_rag'),
        $options,
        [
            'multiple' => false,
            'tags' => false,
            'maxitems' => 1,
            'noselectionstring' => get_string('none'),
        ]
    );
    $mform->setType('local_assign_ai_rag_grader', PARAM_INT);
    $mform->addHelpButton('local_assign_ai_rag_grader', 'autogradegrader', 'local_assign_ai_rag');
    if ($graderdefault) {
        $mform->setDefault('local_assign_ai_rag_grader', (int)$graderdefault);
    }
    $mform->hideIf('local_assign_ai_rag_grader', 'local_assign_ai_rag_autograde', 'neq', 1);
}

/**
 * Persists AI configuration when the assignment form is submitted.
 *
 * @param stdClass $data
 * @param stdClass $course
 * @return stdClass
 */
function local_assign_ai_rag_coursemodule_edit_post_actions($data, $course) {
    global $DB, $USER;

    if ($data->modulename !== 'assign' || empty($data->instance)) {
        return $data;
    }

    $record = $DB->get_record('local_assign_ai_rag_config', ['assignmentid' => $data->instance]);
    $graderid = $record->graderid ?? null;
    if (property_exists($data, 'local_assign_ai_rag_grader')) {
        $value = $data->local_assign_ai_rag_grader;
        if (is_array($value)) {
            $value = reset($value);
        }
        if (!empty($value)) {
            $graderid = (int)$value;
        } else {
            $graderid = null;
        }
    }

    $config = (object)[
        'assignmentid' => $data->instance,
        'autograde' => empty($data->local_assign_ai_rag_autograde) ? 0 : 1,
        'graderid' => $graderid,
        'use_course_materials' => empty($data->local_assign_ai_rag_usematerials) ? 0 : 1,
        'timemodified' => time(),
        'usermodified' => $USER->id ?? null,
    ];

    if ($record) {
        $config->id = $record->id;
        $DB->update_record('local_assign_ai_rag_config', $config);
    } else {
        $config->timecreated = time();
        $DB->insert_record('local_assign_ai_rag_config', $config);
    }

    return $data;
}
