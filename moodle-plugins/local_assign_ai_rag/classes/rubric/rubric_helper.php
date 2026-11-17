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

namespace local_assign_ai_rag\rubric;

/**
 * Rubric helper functions for local_assign_ai_rag.
 *
 * @package     local_assign_ai_rag
 * @copyright   2025 Glenn H. K. M.
 * @license     https://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */
class rubric_helper {
    /**
     * Retrieves the rubric definition and its criteria for a given course module.
     *
     * @param int $cmid The course module ID.
     * @return array|null The rubric details or null if not found.
     */
    public static function get_rubric($cmid) {
        global $DB;

        $context = \context_module::instance($cmid);
        $gradingareas = $DB->get_records('grading_areas', ['contextid' => $context->id]);

        if (!$gradingareas) {
            return null;
        }

        $area = reset($gradingareas);
        $definition = $DB->get_record('grading_definitions', ['areaid' => $area->id]);

        if (!$definition) {
            return null;
        }

        $criteria = $DB->get_records('gradingform_rubric_criteria', ['definitionid' => $definition->id]);

        $rubric = [
            'title' => $definition->name,
            'description' => $definition->description,
            'criteria' => [],
        ];

        foreach ($criteria as $criterion) {
            $levels = $DB->get_records('gradingform_rubric_levels', ['criterionid' => $criterion->id]);
            $crit = ['criterion' => $criterion->description, 'levels' => []];
            foreach ($levels as $level) {
                $crit['levels'][] = [
                    'points' => (int) $level->score,
                    'description' => $level->definition,
                ];
            }
            $rubric['criteria'][] = $crit;
        }

        return $rubric;
    }

    /**
     * Convert Moodle rubric format to RAG server format.
     *
     * @param array|null $rubric Moodle rubric array.
     * @return array RAG-compatible rubric array.
     */
    public static function convert_to_rag_format(?array $rubric): array {
        if (empty($rubric) || empty($rubric['criteria'])) {
            return [];
        }

        $ragRubric = [];
        foreach ($rubric['criteria'] as $criterion) {
            $maxPoints = 0;
            foreach ($criterion['levels'] as $level) {
                if ($level['points'] > $maxPoints) {
                    $maxPoints = $level['points'];
                }
            }
            $ragRubric[] = [
                'name' => $criterion['criterion'],
                'description' => $criterion['criterion'],
                'max_points' => $maxPoints,
                'levels' => $criterion['levels'],
            ];
        }

        return $ragRubric;
    }
}
