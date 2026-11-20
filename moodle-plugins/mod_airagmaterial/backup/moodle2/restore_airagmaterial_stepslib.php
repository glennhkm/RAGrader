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
 * Restore steps for mod_airagmaterial.
 *
 * @package    mod_airagmaterial
 * @category   backup
 * @copyright  2025 Glenn HKM
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

/**
 * Defines the restore structure step for one airagmaterial activity instance.
 *
 * Restores the main airagmaterial record and airagmaterial_files rows.
 * Note: restored instances will have vectorize_status = 'pending' so the teacher
 * must re-vectorize after restore (the actual vector embeddings are not portable).
 */
class restore_airagmaterial_activity_structure_step extends restore_activity_structure_step {

    /**
     * Define the structure of the XML that will be restored.
     *
     * @return array of restore_path_element objects.
     */
    protected function define_structure() {
        $paths = [];

        $paths[] = new restore_path_element('airagmaterial', '/activity/airagmaterial');
        $paths[] = new restore_path_element('airagmaterial_file', '/activity/airagmaterial/files/file');

        return $this->prepare_activity_structure($paths);
    }

    /**
     * Process a restored airagmaterial record.
     *
     * @param array $data Record data from backup XML.
     */
    public function process_airagmaterial($data) {
        global $DB;

        $data = (object)$data;
        $oldid = $data->id;

        $data->course          = $this->get_courseid();
        $data->timecreated     = $this->apply_date_offset($data->timecreated);
        $data->timemodified    = $this->apply_date_offset($data->timemodified);
        // Vector embeddings are not portable — teacher must re-vectorize after restore.
        $data->vectorize_status = 'pending';

        $newid = $DB->insert_record('airagmaterial', $data);
        $this->apply_activity_instance($newid);
        $this->set_mapping('airagmaterial', $oldid, $newid);
    }

    /**
     * Process a restored airagmaterial_files record.
     *
     * @param array $data Record data from backup XML.
     */
    public function process_airagmaterial_file($data) {
        global $DB;

        $data = (object)$data;

        $data->materialid  = $this->get_new_parentid('airagmaterial');
        $data->timecreated = $this->apply_date_offset($data->timecreated);

        $DB->insert_record('airagmaterial_files', $data);
    }

    /**
     * After restore, update related files using the filearea mapping.
     */
    protected function after_execute() {
        $this->add_related_files('mod_airagmaterial', 'intro', null);
        $this->add_related_files('mod_airagmaterial', 'materials', null);
    }
}
