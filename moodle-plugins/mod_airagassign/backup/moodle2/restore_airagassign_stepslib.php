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
 * Restore steps for mod_airagassign.
 *
 * @package    mod_airagassign
 * @category   backup
 * @copyright  2025 Glenn HKM
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

/**
 * Defines the restore structure step for one airagassign activity instance.
 *
 * Restores the main airagassign record, questions, rubric criteria, linked
 * material IDs, and (when userinfo is included) submissions and answers.
 *
 * Note: materialid values in airagassign_materials reference airagmaterial
 * instances that may not exist on the target site — the teacher should review
 * and update the linked materials after restore.
 */
class restore_airagassign_activity_structure_step extends restore_activity_structure_step {

    /**
     * Define the structure of the XML that will be restored.
     *
     * @return array of restore_path_element objects.
     */
    protected function define_structure() {
        $paths = [];
        $userinfo = $this->get_setting_value('userinfo');

        $paths[] = new restore_path_element('airagassign', '/activity/airagassign');
        $paths[] = new restore_path_element('airagassign_question',  '/activity/airagassign/questions/question');
        $paths[] = new restore_path_element('airagassign_criteria',  '/activity/airagassign/criterias/criteria');
        $paths[] = new restore_path_element('airagassign_material',  '/activity/airagassign/materials/material');

        if ($userinfo) {
            $paths[] = new restore_path_element('airagassign_submission', '/activity/airagassign/submissions/submission');
            $paths[] = new restore_path_element('airagassign_answer',
                '/activity/airagassign/submissions/submission/answers/answer');
        }

        return $paths;
    }

    // ── Processors ────────────────────────────────────────────────────────────

    /**
     * Restore the main airagassign record.
     *
     * @param array $data Record data from backup XML.
     */
    public function process_airagassign($data) {
        global $DB;

        $data = (object)$data;
        $oldid = $data->id;

        $data->course       = $this->get_courseid();
        $data->timemodified = $this->apply_date_offset($data->timemodified);
        $data->timecreated  = $this->apply_date_offset($data->timecreated);
        if (!empty($data->opendate)) {
            $data->opendate = $this->apply_date_offset($data->opendate);
        }
        if (!empty($data->duedate)) {
            $data->duedate = $this->apply_date_offset($data->duedate);
        }

        $newid = $DB->insert_record('airagassign', $data);
        $this->apply_activity_instance($newid);
        $this->set_mapping('airagassign', $oldid, $newid);
    }

    /**
     * Restore a quiz question.
     *
     * @param array $data Record data from backup XML.
     */
    public function process_airagassign_question($data) {
        global $DB;

        $data = (object)$data;

        $data->assignid    = $this->get_new_parentid('airagassign');
        $data->timecreated = $this->apply_date_offset($data->timecreated);

        $DB->insert_record('airagassign_questions', $data);
    }

    /**
     * Restore a rubric criterion.
     *
     * @param array $data Record data from backup XML.
     */
    public function process_airagassign_criteria($data) {
        global $DB;

        $data = (object)$data;
        $data->assignid = $this->get_new_parentid('airagassign');

        $DB->insert_record('airagassign_criteria', $data);
    }

    /**
     * Restore a linked material reference.
     *
     * The materialid references an airagmaterial instance which may or may not
     * exist on the target site.  We restore it as-is; the teacher can re-link
     * materials after restore if necessary.
     *
     * @param array $data Record data from backup XML.
     */
    public function process_airagassign_material($data) {
        global $DB;

        $data = (object)$data;
        $data->assignid = $this->get_new_parentid('airagassign');

        // Try to remap to a new materialid if the airagmaterial was also restored.
        $newmaterialid = $this->get_mappingid('airagmaterial', $data->materialid);
        if ($newmaterialid) {
            $data->materialid = $newmaterialid;
        }
        // If the material doesn't exist on this site, skip silently to avoid FK violations.
        if (!$DB->record_exists('airagmaterial', ['id' => $data->materialid])) {
            return;
        }

        $DB->insert_record('airagassign_materials', $data);
    }

    /**
     * Restore a student submission.
     *
     * @param array $data Record data from backup XML.
     */
    public function process_airagassign_submission($data) {
        global $DB;

        $data = (object)$data;
        $oldid = $data->id;

        $data->assignid    = $this->get_new_parentid('airagassign');
        $data->userid      = $this->get_mappingid('user', $data->userid);
        $data->timecreated = $this->apply_date_offset($data->timecreated);
        if (!empty($data->timegraded)) {
            $data->timegraded = $this->apply_date_offset($data->timegraded);
        }
        if (!empty($data->grading_started_at)) {
            $data->grading_started_at = $this->apply_date_offset($data->grading_started_at);
        }

        $newid = $DB->insert_record('airagassign_submissions', $data);
        $this->set_mapping('airagassign_submission', $oldid, $newid);
    }

    /**
     * Restore a per-question answer.
     *
     * @param array $data Record data from backup XML.
     */
    public function process_airagassign_answer($data) {
        global $DB;

        $data = (object)$data;
        $data->submissionid = $this->get_new_parentid('airagassign_submission');

        // Remap questionid to new question IDs if available.
        $newquestionid = $this->get_mappingid('airagassign_question', $data->questionid);
        if ($newquestionid) {
            $data->questionid = $newquestionid;
        }

        $DB->insert_record('airagassign_answers', $data);
    }

    /**
     * After restore, update related intro files.
     */
    protected function after_execute() {
        $this->add_related_files('mod_airagassign', 'intro', null);
        $this->add_related_files('mod_airagassign', 'manualfile', null);
    }
}
