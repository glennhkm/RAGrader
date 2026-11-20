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
 * Language strings (Indonesian) for AI RAG Material module.
 *
 * @package    mod_airagmaterial
 * @copyright  2025 Glenn HKM
 * @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

$string['modulename'] = 'Materi AI RAG';
$string['modulenameplural'] = 'Materi AI RAG';
$string['modulename_help'] = 'Modul Materi AI RAG memungkinkan guru mengunggah materi pembelajaran (PDF, PPTX, DOCX, TXT) yang secara otomatis divektorisasi ke database vektor ChromaDB. Materi ini berfungsi sebagai basis pengetahuan untuk penilaian tugas berbasis AI RAG.';
$string['pluginname'] = 'Materi AI RAG';
$string['pluginadministration'] = 'Administrasi Materi AI RAG';
$string['airagmaterialname'] = 'Nama materi';
$string['airagmaterialname_help'] = 'Masukkan nama deskriptif untuk koleksi materi ini.';
$string['airagmaterialname_placeholder'] = 'contoh: Pertemuan 1 – Pengantar AI';
$string['airagmaterial:addinstance'] = 'Tambah Materi AI RAG baru';
$string['airagmaterial:view'] = 'Lihat Materi AI RAG';
$string['airagmaterial:upload'] = 'Unggah materi untuk vektorisasi';
$string['airagmaterial:manage'] = 'Kelola Materi AI RAG';
$string['materialfiles'] = 'File materi';
$string['materialfiles_help'] = 'Unggah file PDF, PPTX, DOCX, atau TXT yang akan diproses dan disimpan secara otomatis di database vektor untuk penilaian AI RAG. Ukuran maksimal: 50MB per file.';
$string['material_intro_hint'] = 'Unggah materi pembelajaran Anda di sini. File akan secara otomatis divektorisasi ke basis pengetahuan AI setelah disimpan.';
$string['file_section_hint'] = 'Tipe file yang diterima: PDF, PPTX, DOCX, TXT.';
$string['vectorizestatus'] = 'Status vektorisasi';
$string['status_pending'] = 'Menunggu vektorisasi';
$string['status_queued'] = 'Antrian vektorisasi';
$string['status_processing'] = 'Sedang diproses...';;
$string['status_completed'] = 'Berhasil divektorisasi';
$string['status_failed'] = 'Vektorisasi gagal';
$string['totalchunks'] = 'Total chunk yang dibuat';
$string['totaldocuments'] = 'Total dokumen yang dimuat';
$string['vectorizeaction'] = 'Vektorisasi materi';
$string['revectorize'] = 'Vektorisasi ulang';
$string['clearvectors'] = 'Hapus vektor';
$string['confirmclear'] = 'Apakah Anda yakin ingin menghapus semua vektor untuk materi ini? Tindakan ini tidak dapat dibatalkan.';
$string['vectorizesuccess'] = 'Materi berhasil divektorisasi! {$a->chunks} chunk dibuat dari {$a->documents} dokumen.';
$string['vectorizeerror'] = 'Kesalahan vektorisasi materi: {$a}';
$string['autovectorizesuccess'] = 'File otomatis divektorisasi setelah diunggah! {$a->chunks} chunk dibuat dari {$a->documents} dokumen.';
$string['autovectorizeerror'] = 'Vektorisasi otomatis gagal setelah unggah: {$a}. Anda dapat mencoba kembali menggunakan tombol Vektorisasi Ulang.';
$string['autovectorize_info'] = 'File akan secara otomatis divektorisasi saat diunggah. Gunakan tombol Vektorisasi Ulang jika Anda perlu memproses ulang materi.';
$string['nofiles'] = 'Belum ada file yang diunggah.';
$string['uploadedfiles'] = 'File yang diunggah';
$string['filecount'] = '{$a} file diunggah';
$string['maxfilesize'] = 'Ukuran file maksimal: 50MB per file';
$string['allowedfiletypes'] = 'Tipe file yang diperbolehkan: PDF, PPTX, DOCX, TXT';
$string['serverurl'] = 'URL Server RAG';
$string['serverurl_desc'] = 'URL server API RAG (contoh: http://127.0.0.1:8000)';
$string['apikey'] = 'API Key (Opsional)';
$string['apikey_desc'] = 'Token bearer opsional yang sesuai dengan API_AUTH_TOKEN di server API RAG.';
$string['servererror'] = 'Tidak dapat terhubung ke server RAG. Silakan periksa URL server di pengaturan plugin.';
$string['privacy:metadata'] = 'Plugin Materi AI RAG hanya menyimpan materi pembelajaran dan tidak menyimpan data pribadi pengguna. Berkas yang Anda tambahkan dikirim ke server RAG yang dikonfigurasi untuk divektorisasi.';
$string['description'] = 'Deskripsi';
$string['materialsheader'] = 'File materi';
$string['vectorstatus'] = 'Status Database Vektor';
$string['documentsindb'] = 'Dokumen di database vektor';
$string['chunksindb'] = 'Chunk di database vektor';
$string['lastprocessed'] = 'Terakhir diproses';
$string['never'] = 'Belum pernah';
$string['indicator:cognitivedepth'] = 'Kedalaman kognitif Materi AI RAG';
$string['indicator:cognitivedepth_help'] = 'Indikator ini berdasarkan kedalaman kognitif yang dicapai siswa dalam sumber daya Materi AI RAG.';
$string['indicator:socialbreadth'] = 'Keluasan sosial Materi AI RAG';
$string['indicator:socialbreadth_help'] = 'Indikator ini berdasarkan keluasan sosial yang dicapai siswa dalam sumber daya Materi AI RAG.';
$string['search:activity'] = 'Materi AI RAG';
$string['task_vectorize'] = 'Vektorisasi Materi AI RAG';
$string['vectorize_queued_notice'] = 'Vektorisasi telah masuk antrian. Proses akan berjalan di latar belakang — Anda bisa membuka halaman lain dan kembali nanti.';
$string['vectorize_processing_title'] = 'Vektorisasi sedang berlangsung';
$string['queue_navigate_away'] = 'Anda bisa membuka halaman lain dan kembali nanti.';
$string['clearvectors_busy'] = 'Vektor tidak dapat dihapus selama vektorisasi masih dalam antrian atau sedang diproses. Silakan tunggu hingga selesai.';
$string['clearvectors_success'] = 'Vektor untuk materi ini telah dihapus. Materi lain di kursus ini tidak terpengaruh.';
$string['clearvectors_failed'] = 'Server RAG gagal menghapus vektor untuk: {$a}. Silakan coba hapus lagi.';
$string['clearvectors_retained'] = 'Vektor untuk {$a} dipertahankan karena aktivitas lain di kursus ini memakai file dengan nama yang sama.';
$string['stalevectors_cleanup_failed'] = 'Gagal menghapus vektor dari file yang sudah dihapus dari materi ini: {$a}.';
$string['upgrade_revectorize_notice'] = '{$a} materi akan divektorisasi ulang di latar belakang setelah pembaruan ini agar vektornya dimiliki oleh masing-masing materi. Penilaian AI menunggu sampai vektorisasi selesai (materi berstatus antrean sampai saat itu).';
