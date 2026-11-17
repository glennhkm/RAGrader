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
 * Defines backup_airagassign_activity_task class.
 *
 * @package    mod_airagassign
 * @category   backup
 * @copyright  2025 Glenn HKM
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

require_once($CFG->dirroot . '/mod/airagassign/backup/moodle2/backup_airagassign_stepslib.php');

/**
 * Provides the steps to perform one complete backup of the airagassign instance.
 */
class backup_airagassign_activity_task extends backup_activity_task {

    /**
     * No specific settings for this activity.
     */
    protected function define_my_settings() {
    }

    /**
     * Defines backup steps to store the instance data in airagassign.xml.
     */
    protected function define_my_steps() {
        $this->add_step(
            new backup_airagassign_activity_structure_step('airagassign_structure', 'airagassign.xml')
        );
    }

    /**
     * No content encoding needed.
     *
     * @param string $content HTML content that may contain URLs.
     * @return string Unchanged content.
     */
    public static function encode_content_links($content) {
        return $content;
    }
}
