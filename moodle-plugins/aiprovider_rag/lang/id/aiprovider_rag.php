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
 * Language strings for aiprovider_rag (Indonesian).
 *
 * @package     aiprovider_rag
 * @copyright   2025 Glenn H. K. M.
 * @license     https://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

$string['pluginname'] = 'RAG AI Provider';
$string['privacy:metadata'] = 'Plugin RAG AI Provider tidak menyimpan data pribadi apapun.';

// Settings.
$string['serverurl'] = 'URL Server RAG';
$string['serverurl_desc'] = 'URL server RAG (contoh: http://localhost:8000). Server ini menangani penilaian esai dengan konteks materi kuliah.';
$string['serverurl_help'] = 'Masukkan URL lengkap server RAG termasuk protokol (http:// atau https://). Default adalah http://localhost:8000 untuk pengembangan lokal.';
$string['apikey'] = 'Kunci API';
$string['apikey_desc'] = 'Kunci API opsional untuk autentikasi dengan server RAG.';
$string['apikey_help'] = 'Jika server RAG memerlukan autentikasi, masukkan kunci API di sini. Biarkan kosong jika tidak diperlukan autentikasi.';
$string['timeout'] = 'Batas Waktu Request';
$string['timeout_desc'] = 'Waktu maksimum (dalam detik) untuk menunggu respon dari server RAG. Default adalah 120 detik.';
$string['timeout_help'] = 'Jumlah detik maksimum untuk menunggu respon dari server RAG. Tingkatkan nilai ini untuk koneksi lambat atau saat memproses submission besar.';
$string['debug'] = 'Mode Debug';
$string['debug_desc'] = 'Aktifkan logging debug untuk komunikasi API RAG.';

// Services.
$string['service_assign_ai'] = 'Penilaian Tugas dengan AI';

// Actions.
$string['action_assign_answer'] = 'Nilai Jawaban Tugas';
$string['action_grade'] = 'Nilai Esai';
$string['action_upload'] = 'Unggah Materi Kuliah';
$string['action_status'] = 'Status Server';
$string['action_collections'] = 'Kelola Koleksi';

// Error messages.
$string['curlerror'] = 'Error koneksi: {$a}';
$string['httperror'] = 'Server mengembalikan kode error: {$a}';
$string['jsondecodeerror'] = 'Respon tidak valid dari server RAG.';
$string['serverunreachable'] = 'Server RAG tidak dapat dijangkau. Periksa URL server dan pastikan server berjalan.';
$string['invalidresponse'] = 'Respon tidak valid dari server RAG.';
$string['missingconfig'] = 'URL server RAG belum dikonfigurasi.';

// Status messages.
$string['serverhealthy'] = 'Server RAG sehat dan siap.';
$string['serverunhealthy'] = 'Server RAG tidak merespon.';
$string['connectiontest'] = 'Tes Koneksi';
$string['connectiontest_desc'] = 'Tes koneksi ke server RAG.';
$string['connectiontestsuccess'] = 'Koneksi berhasil! Server RAG siap.';
$string['connectiontestfail'] = 'Koneksi gagal: {$a}';

// Grading.
$string['gradingwithrag'] = 'Menilai dengan RAG AI...';
$string['gradingerror'] = 'Error saat penilaian AI: {$a}';
$string['gradingcomplete'] = 'Penilaian AI selesai.';
$string['nomaterialsfound'] = 'Tidak ada materi kuliah ditemukan. Silakan unggah materi terlebih dahulu.';

// Upload.
$string['uploadingmaterials'] = 'Mengunggah materi kuliah...';
$string['uploadcomplete'] = 'Materi berhasil diunggah: {$a} dokumen diproses.';
$string['uploaderror'] = 'Error mengunggah materi: {$a}';

// Collections.
$string['collectioncreated'] = 'Koleksi dibuat untuk mata kuliah.';
$string['collectioncleared'] = 'Koleksi berhasil dihapus.';
$string['collectionstats'] = 'Koleksi berisi {$a} potongan dokumen.';
