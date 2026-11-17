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

use Psr\Http\Message\RequestInterface;

/**
 * Provider class for RAG-based AI integration.
 * 
 * This provider connects Moodle to a RAG (Retrieval-Augmented Generation)
 * server that provides AI-powered essay grading with course material context.
 *
 * @package    aiprovider_rag
 * @copyright  2025 Glenn H. K. M.
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */
// Moodle 4.5 declares get_action_list() as an instance method, while Moodle
// 5.0+ declares it as static. Select the matching adapter at load time so an
// upgrade between those releases cannot cause a PHP signature fatal error.
if ((new \ReflectionMethod(\core_ai\provider::class, 'get_action_list'))->isStatic()) {
    abstract class provider_compat extends \core_ai\provider {
        public static function get_action_list(): array {
            return [];
        }
    }
} else {
    abstract class provider_compat extends \core_ai\provider {
        public function get_action_list(): array {
            return [];
        }
    }
}

/**
 * RAG provider configuration bridge.
 *
 * Assignment grading is handled by local_assign_ai_rag through the structured
 * RAG API. No generic Core AI actions are advertised because the API does not
 * expose generate-text or summarise-text endpoints.
 */
class provider extends provider_compat {

    /**
     * Add authentication headers to the request.
     *
     * @param RequestInterface $request The request to add headers to.
     * @return RequestInterface The modified request.
     */
    public function add_authentication_headers(RequestInterface $request): RequestInterface {
        $apikey = $this->get_provider_config('apikey', '');
        if (!empty($apikey)) {
            return $request->withAddedHeader('Authorization', "Bearer {$apikey}");
        }
        return $request;
    }

    /**
     * Check if the request is allowed by the rate limiter.
     *
     * @param \core_ai\aiactions\base $action The action to check.
     * @return array|bool True on success, array of error details on failure.
     */
    public function is_request_allowed(\core_ai\aiactions\base $action): array|bool {
        return true;
    }

    /**
     * Check if this provider has the minimal configuration to work.
     *
     * @return bool Return true if configured.
     */
    public function is_provider_configured(): bool {
        $serverurl = $this->get_provider_config('serverurl', '');
        return !empty($serverurl);
    }

    /**
     * Get the RAG server URL from configuration.
     *
     * @return string The server URL.
     */
    public function get_server_url(): string {
        $url = $this->get_provider_config('serverurl', 'http://localhost:8000');
        return rtrim($url, '/');
    }

    /**
     * Get the API key from configuration.
     *
     * @return string The API key.
     */
    public function get_api_key(): string {
        return (string) $this->get_provider_config('apikey', '');
    }

    /**
     * Get the timeout setting from configuration.
     *
     * @return int The timeout in seconds.
     */
    public function get_timeout(): int {
        return (int) $this->get_provider_config('timeout', 120);
    }

    /**
     * Check if debug mode is enabled.
     *
     * @return bool True if debug mode is enabled.
     */
    public function is_debug_enabled(): bool {
        $debug = $this->get_provider_config('debug', 0);
        return !empty($debug);
    }

    /**
     * Read instance configuration on Moodle 5.0+, with legacy 4.5 fallback.
     *
     * @param string $name Configuration key.
     * @param mixed $default Default value.
     * @return mixed
     */
    private function get_provider_config(string $name, mixed $default): mixed {
        if (property_exists($this, 'config') && array_key_exists($name, $this->config)) {
            return $this->config[$name];
        }

        $value = get_config('aiprovider_rag', $name);
        return $value === false ? $default : $value;
    }
}
