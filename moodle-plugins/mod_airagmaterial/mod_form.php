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
 * Module form for AI RAG Material.
 *
 * @package    mod_airagmaterial
 * @copyright  2025 Glenn HKM
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

require_once($CFG->dirroot . '/course/moodleform_mod.php');

/**
 * Form for adding/editing AI RAG Material.
 */
class mod_airagmaterial_mod_form extends moodleform_mod {

    /**
     * Define form elements.
     */
    public function definition() {
        global $CFG;

        $mform = $this->_form;

        // ---- General section ----
        $mform->addElement('header', 'general', get_string('general', 'form'));

        $mform->addElement('html', '<p class="text-muted small mb-3">Give this material collection a clear name, then upload your course files below. After saving, click <strong>"Vectorize materials"</strong> on the view page to enable AI grading.</p>');
        $mform->addElement('text', 'name', get_string('airagmaterialname', 'airagmaterial'),
            ['size' => '64',
             'placeholder' => get_string('airagmaterialname_placeholder', 'airagmaterial')]);
        $mform->setType('name', PARAM_TEXT);
        $mform->addRule('name', null, 'required', null, 'client');
        $mform->addRule('name', get_string('maximumchars', '', 255), 'maxlength', 255, 'client');
        $mform->addHelpButton('name', 'airagmaterialname', 'airagmaterial');

        $this->standard_intro_elements();

        // ---- Material files section ----
        $mform->addElement('header', 'materialshdr', get_string('materialsheader', 'airagmaterial'));
        $mform->addElement('html', '<p class="text-muted small mb-3">' . get_string('material_intro_hint', 'airagmaterial') .
            ' Supported formats: PDF, PPTX, DOCX, TXT.</p>');

        $fileoptions = [
            'subdirs'        => false,
            'maxbytes'       => AIRAGMATERIAL_MAX_FILESIZE,
            'maxfiles'       => 20,
            'accepted_types' => explode(',', AIRAGMATERIAL_ALLOWED_TYPES),
        ];
        $mform->addElement('filemanager', 'materialfiles', get_string('materialfiles', 'airagmaterial'), null, $fileoptions);
        $mform->addHelpButton('materialfiles', 'materialfiles', 'airagmaterial');
        $mform->addRule('materialfiles', get_string('required'), 'required', null, 'client');

        $mform->addElement('html', '<p class="text-muted small mt-1">' . get_string('file_section_hint', 'airagmaterial') .
            ' ' . get_string('maxfilesize', 'airagmaterial') . '. Up to 20 files.</p>');

        // ---- Standard course module elements ----
        $this->standard_coursemodule_elements();

        // ---- Action buttons ----
        $this->add_action_buttons();
    }

    /**
     * Preprocess form data for editing.
     *
     * @param array $defaultvalues Default values
     */
    public function data_preprocessing(&$defaultvalues) {
        if ($this->current->instance) {
            $draftitemid = file_get_submitted_draft_itemid('materialfiles');
            file_prepare_draft_area(
                $draftitemid,
                $this->context->id,
                'mod_airagmaterial',
                'materials',
                0,
                airagmaterial_get_filemanager_options()
            );
            $defaultvalues['materialfiles'] = $draftitemid;
        }
    }

    /**
     * Validate form data.
     *
     * @param array $data Form data
     * @param array $files Files
     * @return array Validation errors
     */
    public function validation($data, $files) {
        $errors = parent::validation($data, $files);

        // Validate that files were uploaded.
        if (isset($data['materialfiles'])) {
            $draftitemid = $data['materialfiles'];
            $draftfiles = file_get_drafarea_files($draftitemid);
            if (empty($draftfiles->list)) {
                $errors['materialfiles'] = get_string('required');
            }
        }

        return $errors;
    }
}
