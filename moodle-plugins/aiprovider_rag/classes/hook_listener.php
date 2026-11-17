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

namespace aiprovider_rag;

use core_ai\hook\after_ai_provider_form_hook;

/**
 * Hook listener for RAG AI provider.
 *
 * @package    aiprovider_rag
 * @copyright  2025 Glenn H. K. M.
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */
class hook_listener {

    /**
     * Hook listener for the RAG AI instance setup form.
     *
     * This adds the configuration fields when creating a new RAG AI provider instance
     * through Site Administration > AI > AI providers.
     *
     * @param after_ai_provider_form_hook $hook The hook to add to the AI instance setup.
     */
    public static function set_form_definition_for_aiprovider_rag(after_ai_provider_form_hook $hook): void {
        if ($hook->plugin !== 'aiprovider_rag') {
            return;
        }

        $mform = $hook->mform;

        // RAG Server URL setting (required).
        $mform->addElement(
            'text',
            'serverurl',
            get_string('serverurl', 'aiprovider_rag'),
            ['size' => 75],
        );
        $mform->setType('serverurl', PARAM_URL);
        $mform->setDefault('serverurl', 'http://localhost:8000');
        $mform->addHelpButton('serverurl', 'serverurl', 'aiprovider_rag');
        $mform->addRule('serverurl', get_string('required'), 'required', null, 'client');

        // API Key setting (optional).
        $mform->addElement(
            'passwordunmask',
            'apikey',
            get_string('apikey', 'aiprovider_rag'),
            ['size' => 50],
        );
        $mform->addHelpButton('apikey', 'apikey', 'aiprovider_rag');

        // Request timeout setting.
        $mform->addElement(
            'text',
            'timeout',
            get_string('timeout', 'aiprovider_rag'),
            ['size' => 10],
        );
        $mform->setType('timeout', PARAM_INT);
        $mform->setDefault('timeout', 120);
        $mform->addHelpButton('timeout', 'timeout', 'aiprovider_rag');

        // Debug mode setting.
        $mform->addElement(
            'advcheckbox',
            'debug',
            get_string('debug', 'aiprovider_rag'),
            get_string('debug_desc', 'aiprovider_rag'),
        );
        $mform->setDefault('debug', 0);
    }
}
