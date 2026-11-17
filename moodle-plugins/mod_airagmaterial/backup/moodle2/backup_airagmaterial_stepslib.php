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
 * Backup steps for mod_airagmaterial.
 *
 * @package    mod_airagmaterial
 * @category   backup
 * @copyright  2025 Glenn HKM
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

/**
 * Defines the backup structure step for one airagmaterial activity instance.
 *
 * Backs up the main airagmaterial record and its associated file-tracking rows
 * (airagmaterial_files).  The actual uploaded files are backed up automatically
 * by Moodle's file API because they live in the 'materials' filearea.
 */
class backup_airagmaterial_activity_structure_step extends backup_activity_structure_step {

    /**
     * Define the structure of the backup XML for this activity.
     *
     * @return backup_nested_element The root element of the backup structure.
     */
    protected function define_structure() {

        // ── Root element: airagmaterial ───────────────────────────────────────
        $airagmaterial = new backup_nested_element('airagmaterial', ['id'], [
            'name',
            'intro',
            'introformat',
            'vectorize_status',
            'timecreated',
            'timemodified',
        ]);

        // ── Child: tracked uploaded files ─────────────────────────────────────
        $files = new backup_nested_element('files');
        $file  = new backup_nested_element('file', ['id'], [
            'filename',
            'filepath',
            'timecreated',
        ]);

        // Build tree.
        $airagmaterial->add_child($files);
        $files->add_child($file);

        // ── Wire to DB tables ─────────────────────────────────────────────────
        $airagmaterial->set_source_table('airagmaterial', ['id' => backup::VAR_ACTIVITYID]);
        $file->set_source_table('airagmaterial_files', ['materialid' => backup::VAR_PARENTID]);

        // ── Return wrapped root element ───────────────────────────────────────
        return $this->prepare_activity_structure($airagmaterial);
    }
}
