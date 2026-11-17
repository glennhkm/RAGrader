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

/**
 * Plugin administration pages are defined here.
 *
 * @package     local_assign_ai_rag
 * @category    admin
 * @copyright   2025 Glenn H. K. M.
 * @license     https://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

if ($hassiteconfig) {
    $settings = new admin_settingpage('local_assign_ai_rag_settings', new lang_string('pluginname', 'local_assign_ai_rag'));

    if ($ADMIN->fulltree) {
        // RAG Server Settings header.
        $settings->add(new admin_setting_heading(
            'local_assign_ai_rag/serverheading',
            get_string('serverheading', 'local_assign_ai_rag'),
            get_string('serverheading_desc', 'local_assign_ai_rag')
        ));

        // Server URL.
        $settings->add(new admin_setting_configtext(
            'local_assign_ai_rag/server_url',
            get_string('serverurl', 'local_assign_ai_rag'),
            get_string('serverurl_desc', 'local_assign_ai_rag'),
            'http://localhost:8000',
            PARAM_URL
        ));

        // API Key (optional).
        $settings->add(new admin_setting_configpasswordunmask(
            'local_assign_ai_rag/api_key',
            get_string('apikey', 'local_assign_ai_rag'),
            get_string('apikey_desc', 'local_assign_ai_rag'),
            ''
        ));

        // Request timeout.
        $settings->add(new admin_setting_configtext(
            'local_assign_ai_rag/timeout',
            get_string('timeout', 'local_assign_ai_rag'),
            get_string('timeout_desc', 'local_assign_ai_rag'),
            120,
            PARAM_INT
        ));

        // Grading Settings header.
        $settings->add(new admin_setting_heading(
            'local_assign_ai_rag/gradingheading',
            get_string('gradingheading', 'local_assign_ai_rag'),
            get_string('gradingheading_desc', 'local_assign_ai_rag')
        ));

        // Default auto-grade setting.
        $settings->add(new admin_setting_configcheckbox(
            'local_assign_ai_rag/default_autograde',
            get_string('defaultautograde', 'local_assign_ai_rag'),
            get_string('defaultautograde_desc', 'local_assign_ai_rag'),
            0
        ));

        // Default use materials setting.
        $settings->add(new admin_setting_configcheckbox(
            'local_assign_ai_rag/default_usematerials',
            get_string('defaultusematerials', 'local_assign_ai_rag'),
            get_string('defaultusematerials_desc', 'local_assign_ai_rag'),
            1
        ));
    }

    $ADMIN->add('localplugins', $settings);
}
