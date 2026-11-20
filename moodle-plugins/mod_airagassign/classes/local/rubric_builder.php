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

namespace mod_airagassign\local;

/**
 * Builds the rubric dictionary sent to the RAG grading API.
 *
 * @package    mod_airagassign
 * @copyright  2026 RAGrader
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */
class rubric_builder {
    /**
     * Build the rubric dictionary for an assignment.
     *
     * Custom mode uses the activity's own criteria, 'moodle' mode reads Moodle's
     * native advanced grading rubric and 'simple' mode sends no rubric.
     *
     * @param int $assignid Assignment ID
     * @return array Rubric dictionary: name => ['description' => string, 'max_score' => float]
     */
    public static function build(int $assignid): array {
        global $DB;

        $assign = $DB->get_record('airagassign', ['id' => $assignid]);
        if (!$assign) {
            return [];
        }

        $rubricmode = $assign->rubricmode ?? 'custom';
        if ($rubricmode === 'moodle') {
            return self::build_moodle($assign);
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
     * @param \stdClass $assign The assignment instance.
     * @return array Rubric dictionary ([] when no rubric is active and defined)
     */
    public static function build_moodle(\stdClass $assign): array {
        global $CFG;
        require_once($CFG->dirroot . '/grade/grading/lib.php');

        $cm = get_coursemodule_from_instance('airagassign', $assign->id);
        if (!$cm) {
            return [];
        }

        $context = \context_module::instance($cm->id);
        $gradingmanager = get_grading_manager($context, 'mod_airagassign', 'submissions');
        if (!$gradingmanager) {
            return [];
        }

        // Grading controllers expose no public method name, so ask the manager.
        $controller = $gradingmanager->get_active_controller();
        if (!$controller || $gradingmanager->get_active_method() !== 'rubric') {
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

            $rubric[$name] = [
                'description' => implode("\n", $leveldescriptions),
                'max_score' => $maxscore,
            ];
        }

        return $rubric;
    }

    /**
     * Synchronize the selected Moodle advanced grading method.
     *
     * This only enables/disables Moodle native Rubric for the grade item. It must
     * not create or overwrite rubric definitions, because those criteria should be
     * configured by the teacher through Moodle's Advanced grading UI.
     *
     * @param \stdClass $data Form data or assignment instance data (id, rubricmode)
     */
    public static function sync_moodle(\stdClass $data): void {
        global $CFG;

        $cm = get_coursemodule_from_instance('airagassign', $data->id, 0, false, IGNORE_MISSING);
        if (!$cm) {
            return;
        }
        $context = \context_module::instance($cm->id);

        require_once($CFG->dirroot . '/grade/grading/lib.php');
        $gradingmanager = get_grading_manager($context, 'mod_airagassign', 'submissions');

        if (($data->rubricmode ?? '') !== 'moodle') {
            // Not Moodle native rubric: make sure advanced grading is disabled (simple direct grading).
            if (!empty($gradingmanager->get_active_method())) {
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
}
