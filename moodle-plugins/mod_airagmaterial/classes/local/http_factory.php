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

namespace mod_airagmaterial\local;

/**
 * Builds the Guzzle client used to talk to the RAG server.
 *
 * Exists as a separate class so tests can replace it through \core\di.
 *
 * @package    mod_airagmaterial
 * @copyright  2026 RAGrader
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */
class http_factory {
    /**
     * Create an HTTP client.
     *
     * @param int $timeout Request timeout in seconds.
     * @return \GuzzleHttp\ClientInterface
     */
    public function create(int $timeout): \GuzzleHttp\ClientInterface {
        return new \core\http_client([
            'ignoresecurity' => true,
            'timeout' => $timeout,
            'connect_timeout' => 30,
        ]);
    }
}
