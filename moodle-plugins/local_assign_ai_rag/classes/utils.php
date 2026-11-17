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

namespace local_assign_ai_rag;

/**
 * Utility functions for local_assign_ai_rag.
 *
 * @package     local_assign_ai_rag
 * @copyright   2025 Glenn H. K. M.
 * @license     https://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */
class utils {
    /**
     * Normalize the payload for the RAG API.
     * 
     * Ensures all required fields are present and properly formatted.
     *
     * @param array $payload Original payload.
     * @return array Normalized payload.
     */
    public static function normalize_payload(array $payload): array {
        // Strip HTML tags from submission if present
        if (isset($payload['submission_assign'])) {
            $payload['submission_assign'] = strip_tags($payload['submission_assign']);
            $payload['submission_assign'] = html_entity_decode($payload['submission_assign'], ENT_QUOTES, 'UTF-8');
            $payload['submission_assign'] = trim($payload['submission_assign']);
        }

        // Strip HTML from assignment description
        if (isset($payload['assignment_description'])) {
            $payload['assignment_description'] = strip_tags($payload['assignment_description']);
            $payload['assignment_description'] = html_entity_decode($payload['assignment_description'], ENT_QUOTES, 'UTF-8');
            $payload['assignment_description'] = trim($payload['assignment_description']);
        }

        // Ensure rubric is properly formatted
        if (isset($payload['rubric']) && is_string($payload['rubric'])) {
            $decoded = json_decode($payload['rubric'], true);
            if (json_last_error() === JSON_ERROR_NONE) {
                $payload['rubric'] = $decoded;
            }
        }

        // Set default language
        if (!isset($payload['lang'])) {
            $payload['lang'] = current_language();
        }

        // Ensure numeric values
        if (isset($payload['maximum_grade'])) {
            $payload['maximum_grade'] = (float) $payload['maximum_grade'];
        }

        return $payload;
    }

    /**
     * Get the assignment question from various sources.
     * 
     * Tries to extract a meaningful question from assignment intro,
     * activity attachments, or falls back to assignment name.
     *
     * @param \stdClass $assignment Assignment instance.
     * @param \context_module $context Module context.
     * @return string The question/prompt.
     */
    public static function extract_question(\stdClass $assignment, \context_module $context): string {
        // First try: Use assignment intro/description
        if (!empty($assignment->intro)) {
            $question = strip_tags($assignment->intro);
            $question = html_entity_decode($question, ENT_QUOTES, 'UTF-8');
            $question = trim($question);
            
            if (strlen($question) > 20) {
                return $question;
            }
        }

        // Second try: Look for activity attachments
        $fs = get_file_storage();
        $files = $fs->get_area_files(
            $context->id,
            'mod_assign',
            'introattachment',
            0,
            'filename',
            false
        );

        if (!empty($files)) {
            // If there are attachments, mention them
            $filenames = [];
            foreach ($files as $file) {
                $filenames[] = $file->get_filename();
            }
            return $assignment->name . "\n\n(Lampiran: " . implode(', ', $filenames) . ")";
        }

        // Fallback: Use assignment name
        return $assignment->name;
    }

    /**
     * Format the rubric for display or logging.
     *
     * @param array $rubric Rubric structure.
     * @return string Formatted rubric text.
     */
    public static function format_rubric_text(array $rubric): string {
        if (empty($rubric)) {
            return 'Tidak ada rubrik.';
        }

        $output = [];
        
        if (isset($rubric['title'])) {
            $output[] = "Rubrik: " . $rubric['title'];
        }

        if (isset($rubric['criteria'])) {
            foreach ($rubric['criteria'] as $index => $criterion) {
                $critname = $criterion['criterion'] ?? "Kriteria " . ($index + 1);
                $output[] = "\n" . ($index + 1) . ". " . $critname;
                
                if (isset($criterion['levels'])) {
                    foreach ($criterion['levels'] as $level) {
                        $points = $level['points'] ?? 0;
                        $desc = $level['description'] ?? '';
                        $output[] = "   - {$points} poin: {$desc}";
                    }
                }
            }
        }

        return implode("\n", $output);
    }

    /**
     * Calculate confidence color based on score.
     *
     * @param float $confidence Confidence score (0-1).
     * @return string CSS color class.
     */
    public static function confidence_color(float $confidence): string {
        if ($confidence >= 0.8) {
            return 'text-success';
        } elseif ($confidence >= 0.5) {
            return 'text-warning';
        } else {
            return 'text-danger';
        }
    }

    /**
     * Format citations for display.
     *
     * @param array $citations Array of citation objects.
     * @return string HTML formatted citations.
     */
    public static function format_citations(array $citations): string {
        if (empty($citations)) {
            return '';
        }

        $html = '<div class="rag-citations mt-3">';
        $html .= '<h6>Referensi dari Materi Kuliah:</h6>';
        $html .= '<ul class="list-unstyled">';

        foreach ($citations as $index => $citation) {
            $source = $citation['source'] ?? 'Tidak diketahui';
            $page = isset($citation['page']) ? " (hal. {$citation['page']})" : '';
            $text = $citation['text'] ?? '';
            
            $html .= '<li class="mb-2">';
            $html .= '<small class="text-muted">[' . ($index + 1) . '] ' . htmlspecialchars($source) . $page . '</small>';
            if (!empty($text)) {
                $html .= '<br><em>"' . htmlspecialchars(substr($text, 0, 200)) . '..."</em>';
            }
            $html .= '</li>';
        }

        $html .= '</ul></div>';
        return $html;
    }

    /**
     * Get course materials from file areas.
     *
     * @param int $courseid Course ID.
     * @return array Array of file information.
     */
    public static function get_course_materials(int $courseid): array {
        global $DB;

        $materials = [];
        $context = \context_course::instance($courseid);

        // Get course files
        $fs = get_file_storage();

        // Look in various areas for course materials
        $areas = [
            ['component' => 'mod_resource', 'filearea' => 'content'],
            ['component' => 'mod_folder', 'filearea' => 'content'],
            ['component' => 'mod_assign', 'filearea' => 'introattachment'],
            ['component' => 'course', 'filearea' => 'section'],
        ];

        // Get all course module contexts
        $cms = $DB->get_records('course_modules', ['course' => $courseid]);
        
        foreach ($cms as $cm) {
            $cmcontext = \context_module::instance($cm->id);
            
            foreach ($areas as $area) {
                $files = $fs->get_area_files(
                    $cmcontext->id,
                    $area['component'],
                    $area['filearea'],
                    false,
                    'filename',
                    false
                );

                foreach ($files as $file) {
                    // Only include PDFs and documents
                    $mimetype = $file->get_mimetype();
                    if (in_array($mimetype, [
                        'application/pdf',
                        'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                        'application/vnd.ms-powerpoint',
                        'application/msword',
                        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    ])) {
                        $materials[] = [
                            'id' => $file->get_id(),
                            'filename' => $file->get_filename(),
                            'mimetype' => $mimetype,
                            'filesize' => $file->get_filesize(),
                            'contextid' => $cmcontext->id,
                            'component' => $area['component'],
                            'filearea' => $area['filearea'],
                        ];
                    }
                }
            }
        }

        return $materials;
    }
}
