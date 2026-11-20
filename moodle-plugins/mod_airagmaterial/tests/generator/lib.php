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

/**
 * Data generator for mod_airagmaterial.
 *
 * @package    mod_airagmaterial
 * @category   test
 * @copyright  2026 RAGrader
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

/**
 * Data generator class for mod_airagmaterial.
 *
 * @package    mod_airagmaterial
 * @category   test
 * @copyright  2026 RAGrader
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */
class mod_airagmaterial_generator extends testing_module_generator {
    /**
     * Create a material instance without any files (so no vectorization request is made).
     *
     * The status is whatever airagmaterial_add_instance() produces ('queued') unless the
     * record explicitly sets vectorize_status.
     *
     * @param stdClass|array|null $record Instance fields to override.
     * @param array|null $options Course module options.
     * @return stdClass The created instance record (with cmid).
     */
    public function create_instance($record = null, ?array $options = null) {
        global $DB;

        $record = (object)(array)$record;
        $status = $record->vectorize_status ?? null;
        unset($record->vectorize_status);

        $instance = parent::create_instance($record, (array)$options);

        // The add_instance callback ignores any supplied status (it queues a vectorize
        // task and marks the row as queued). Only an explicit request overrides that.
        if ($status !== null) {
            $DB->set_field('airagmaterial', 'vectorize_status', $status, ['id' => $instance->id]);
            $instance->vectorize_status = $status;
        }

        return $instance;
    }

    /**
     * Store a file in the material's file area.
     *
     * @param stdClass $material Instance record as returned by create_instance().
     * @param string $filename File name.
     * @param string $content File content.
     * @return stored_file
     */
    public function create_file(stdClass $material, string $filename, string $content): stored_file {
        $context = context_module::instance($material->cmid);
        return get_file_storage()->create_file_from_string([
            'contextid' => $context->id,
            'component' => 'mod_airagmaterial',
            'filearea' => 'materials',
            'itemid' => 0,
            'filepath' => '/',
            'filename' => $filename,
        ], $content);
    }
}
