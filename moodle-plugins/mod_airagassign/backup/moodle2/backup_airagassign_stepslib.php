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
 * Backup steps for mod_airagassign.
 *
 * @package    mod_airagassign
 * @category   backup
 * @copyright  2025 Glenn HKM
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

/**
 * Defines the backup structure step for one airagassign activity instance.
 *
 * Backs up the main airagassign record, its questions, rubric criteria,
 * linked material IDs, and student submissions with per-answer scores.
 */
class backup_airagassign_activity_structure_step extends backup_activity_structure_step {

    /**
     * Define the structure of the backup XML for this activity.
     *
     * @return backup_nested_element The root element of the backup structure.
     */
    protected function define_structure() {

        $userinfo = $this->get_setting_value('userinfo');

        // ── Root element ──────────────────────────────────────────────────────
        $airagassign = new backup_nested_element('airagassign', ['id'], [
            'course',
            'name',
            'intro',
            'introformat',
            'assignmode',
            'maximumgrade',
            'opendate',
            'duedate',
            'allowlate',
            'rubricmode',
            'essayprompt',
            'minwords',
            'maxwords',
            'timemodified',
            'timecreated',
        ]);

        // ── Questions (quiz mode) ─────────────────────────────────────────────
        $questions = new backup_nested_element('questions');
        $question  = new backup_nested_element('question', ['id'], [
            'questiontext',
            'sortorder',
            'timecreated',
        ]);

        // ── Rubric criteria ───────────────────────────────────────────────────
        $criterias = new backup_nested_element('criterias');
        $criteria  = new backup_nested_element('criteria', ['id'], [
            'name',
            'description',
            'maxscore',
            'sortorder',
        ]);

        // ── Linked material IDs ───────────────────────────────────────────────
        $materials = new backup_nested_element('materials');
        $material  = new backup_nested_element('material', ['id'], [
            'materialid',
        ]);

        // ── Student submissions (user data) ───────────────────────────────────
        $submissions = new backup_nested_element('submissions');
        $submission  = new backup_nested_element('submission', ['id'], [
            'userid',
            'status',
            'grade',
            'ai_grade',
            'ai_feedback',
            'feedback',
            'ai_response',
            'graded_by',
            'teacher_note',
            'confidence',
            'grading_error',
            'grading_requestid',
            'grading_started_at',
            'timecreated',
            'timegraded',
        ]);

        // ── Per-question answers ──────────────────────────────────────────────
        $answers = new backup_nested_element('answers');
        $answer  = new backup_nested_element('answer', ['id'], [
            'questionid',
            'answertext',
            'score',
            'ai_score',
            'ai_feedback',
            'feedback',
            'ai_response',
        ]);

        // ── Build tree ────────────────────────────────────────────────────────
        $airagassign->add_child($questions);
        $questions->add_child($question);

        $airagassign->add_child($criterias);
        $criterias->add_child($criteria);

        $airagassign->add_child($materials);
        $materials->add_child($material);

        $airagassign->add_child($submissions);
        $submissions->add_child($submission);
        $submission->add_child($answers);
        $answers->add_child($answer);

        // ── Wire to DB tables ─────────────────────────────────────────────────
        $airagassign->set_source_table('airagassign', ['id' => backup::VAR_ACTIVITYID]);
        $question->set_source_table('airagassign_questions', ['assignid' => backup::VAR_PARENTID]);
        $criteria->set_source_table('airagassign_criteria', ['assignid' => backup::VAR_PARENTID]);
        $material->set_source_table('airagassign_materials', ['assignid' => backup::VAR_PARENTID]);

        if ($userinfo) {
            $submission->set_source_table('airagassign_submissions', ['assignid' => backup::VAR_PARENTID]);
            $answer->set_source_table('airagassign_answers', ['submissionid' => backup::VAR_PARENTID]);
        }

        // Annotate user IDs for user-data remapping on restore.
        $submission->annotate_ids('user', 'userid');
        $airagassign->annotate_files('mod_airagassign', 'manualfile', null);

        // ── Return wrapped root element ───────────────────────────────────────
        return $this->prepare_activity_structure($airagassign);
    }
}
