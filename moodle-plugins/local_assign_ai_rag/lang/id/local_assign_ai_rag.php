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
 * Language strings for local_assign_ai_rag (Indonesian).
 *
 * @package     local_assign_ai_rag
 * @copyright   2025 Glenn H. K. M.
 * @license     https://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later
 */

defined('MOODLE_INTERNAL') || die();

$string['pluginname'] = 'Penilaian Tugas AI dengan RAG';
$string['privacy:metadata'] = 'Plugin RAG Assignment AI menyimpan nilai AI yang tertunda sementara.';

// Settings page.
$string['settings'] = 'Pengaturan RAG Assignment AI';
$string['serverheading'] = 'Konfigurasi Server RAG';
$string['serverheading_desc'] = 'Konfigurasi koneksi ke server penilaian RAG.';
$string['serverurl'] = 'URL Server';
$string['serverurl_desc'] = 'URL server penilaian RAG (contoh: http://localhost:8000).';
$string['apikey'] = 'API Key';
$string['apikey_desc'] = 'API key opsional untuk autentikasi dengan server RAG.';
$string['timeout'] = 'Request Timeout';
$string['timeout_desc'] = 'Waktu maksimum dalam detik untuk menunggu respons dari server RAG.';
$string['gradingheading'] = 'Pengaturan Penilaian Default';
$string['gradingheading_desc'] = 'Pengaturan default untuk tugas baru.';
$string['defaultautograde'] = 'Aktifkan auto-grading secara default';
$string['defaultautograde_desc'] = 'Jika diaktifkan, tugas baru akan memiliki auto-grading aktif secara default.';
$string['defaultusematerials'] = 'Gunakan materi kuliah secara default';
$string['defaultusematerials_desc'] = 'Jika diaktifkan, tugas baru akan menggunakan materi kuliah (RAG) secara default.';

// Assignment form settings.
$string['aiconfigheader'] = 'Konfigurasi Penilaian RAG AI';
$string['autograde'] = 'Aktifkan RAG AI Auto-grading';
$string['autograde_help'] = 'Jika diaktifkan, pengumpulan akan dinilai secara otomatis menggunakan RAG AI dengan materi kuliah sebagai konteks.';
$string['usecoursematerials'] = 'Gunakan Materi Kuliah (RAG)';
$string['usecoursematerials_help'] = 'Jika diaktifkan, AI akan menggunakan materi kuliah yang diunggah untuk memberikan penilaian dengan kutipan.';
$string['autogradegrader'] = 'Penilai untuk nilai AI';
$string['autogradegrader_help'] = 'Pilih pengguna yang akan dicatat sebagai penilai untuk nilai yang dihasilkan AI.';

// Status messages.
$string['processing'] = 'Memproses dengan RAG AI...';
$string['gradingcomplete'] = 'Penilaian AI selesai.';
$string['gradingerror'] = 'Error saat penilaian AI: {$a}';
$string['serverunavailable'] = 'Server RAG tidak tersedia. Silakan coba lagi nanti.';

// UI strings.
$string['reviewwithai'] = 'Review dengan AI';
$string['reviewall'] = 'Review semua yang tertunda';
$string['approve'] = 'Setujui';
$string['reject'] = 'Tolak';
$string['pending'] = 'Menunggu review';
$string['approved'] = 'Disetujui';
$string['rejected'] = 'Ditolak';

// Grading.
$string['aigrade'] = 'Nilai AI';
$string['aifeedback'] = 'Feedback AI';
$string['confidence'] = 'Tingkat Keyakinan';
$string['citations'] = 'Kutipan dari materi kuliah';
$string['nocitations'] = 'Tidak ada kutipan tersedia.';
$string['retrieveddocs'] = 'Dokumen yang diambil';

// Materials.
$string['uploadmaterials'] = 'Unggah materi kuliah';
$string['uploadmaterials_desc'] = 'Unggah file PDF/PPTX untuk digunakan sebagai konteks penilaian.';
$string['materialscount'] = 'Materi di knowledge base: {$a}';
$string['nomaterials'] = 'Belum ada materi kuliah yang diunggah.';
$string['clearmaterials'] = 'Hapus semua materi';
$string['clearmaterialsconfirm'] = 'Apakah Anda yakin ingin menghapus semua materi kuliah? Ini tidak dapat dibatalkan.';

// Tasks.
$string['taskprocesssubmission'] = 'Proses pengumpulan dengan RAG AI';
$string['taskprocessall'] = 'Proses semua pengumpulan yang tertunda';

// Events.
$string['eventsubmissiongraded'] = 'Pengumpulan dinilai oleh AI';
$string['eventsubmissionapproved'] = 'Nilai AI disetujui';
$string['eventsubmissionrejected'] = 'Nilai AI ditolak';

// Errors.
$string['error:nosubmission'] = 'Pengumpulan tidak ditemukan.';
$string['error:notsubmitted'] = 'Pengumpulan belum disubmit.';
$string['error:alreadygraded'] = 'Pengumpulan sudah dinilai.';
$string['error:serverconnection'] = 'Tidak dapat terhubung ke server RAG.';
$string['error:invalidresponse'] = 'Respons tidak valid dari server RAG.';
$string['error:invaliduploadfile'] = 'Unggahan materi berisi file yang tidak valid.';
$string['error:materialuploadfailed'] = 'Materi tidak dapat diunggah: {$a}';

// Review page - additional.
$string['reviewpage'] = 'Review AI';
$string['reviewpagetitle'] = 'Review Pengumpulan dengan RAG AI';
$string['nosubmissions'] = 'Tidak ada pengumpulan untuk direview.';
$string['student'] = 'Mahasiswa';
$string['submissionstatus'] = 'Status Pengumpulan';
$string['aistatus'] = 'Status AI';
$string['actions'] = 'Aksi';
$string['viewdetails'] = 'Lihat Detail';
$string['reviewsubmission'] = 'Review dengan AI';
$string['approvegrade'] = 'Setujui Nilai';
$string['rejectgrade'] = 'Tolak Nilai';
$string['initial'] = 'Belum direview';
$string['queued'] = 'Dalam antrian';

// Review action messages.
$string['reviewsuccess'] = 'Pengumpulan telah direview oleh AI. Lihat hasilnya di bawah.';
$string['reviewerror'] = 'Error saat review AI';

// View result page.
$string['viewresult'] = 'Hasil Penilaian AI';
$string['backtoreview'] = 'Kembali ke Review';
$string['studentinfo'] = 'Informasi Mahasiswa';
$string['name'] = 'Nama';
$string['email'] = 'Email';
$string['submissiontime'] = 'Waktu Pengumpulan';
$string['submittedfiles'] = 'File yang Dikumpulkan';
$string['onlinetext'] = 'Teks Online';
$string['airesult'] = 'Hasil Penilaian AI';
$string['status'] = 'Status';
$string['feedback'] = 'Feedback';
$string['criterionscores'] = 'Nilai per Kriteria';
$string['criterion'] = 'Kriteria';
$string['score'] = 'Nilai';
$string['assignment'] = 'Tugas';
$string['approvehint'] = 'Menyetujui akan mengirim nilai dan feedback AI ke buku nilai mahasiswa.';
$string['gradeapproved'] = 'Nilai telah disetujui dan dikirim ke mahasiswa.';
$string['graderejected'] = 'Nilai ditolak. Pengumpulan telah direset untuk review ulang.';
$string['alreadyapproved'] = 'Nilai ini sudah disetujui dan dikirim ke mahasiswa.';
$string['notreviewedyet'] = 'Pengumpulan ini belum direview dengan AI. Silakan review terlebih dahulu.';

// Rubric editor.
$string['rubriceditor'] = 'Editor Rubrik RAG';
$string['rubricinfo'] = 'Rubrik Kustom untuk Penilaian RAG AI';
$string['rubricinfodesc'] = 'Tentukan rubrik kustom yang akan digunakan oleh RAG AI untuk penilaian. Setiap kriteria harus memiliki poin, deskripsi, dan definisi level.';
$string['maxgrade'] = 'Nilai Maksimum';
$string['maxgradehint'] = 'Total nilai maksimum untuk tugas ini.';
$string['rubriccriteria'] = 'Kriteria Rubrik';
$string['addcriterion'] = 'Tambah Kriteria';
$string['rubricjson'] = 'Rubrik JSON (Lanjutan)';
$string['rubricjsonhint'] = 'Anda dapat langsung mengedit JSON jika diinginkan. Perubahan akan disinkronkan dengan editor visual.';
$string['saverubric'] = 'Simpan Rubrik';
$string['resettodefault'] = 'Reset ke Default';
$string['deleterubric'] = 'Hapus Rubrik';
$string['confirmdelete'] = 'Apakah Anda yakin ingin menghapus rubrik ini?';
$string['rubricsaved'] = 'Rubrik berhasil disimpan.';
$string['rubricdeleted'] = 'Rubrik dihapus.';
$string['invalidjson'] = 'Format JSON tidak valid. Silakan periksa rubrik Anda.';
$string['invalidrubricstructure'] = 'Struktur rubrik tidak valid. Harus memiliki objek "criteria".';
$string['exampleformat'] = 'Contoh Format Rubrik';
$string['editrubric'] = 'Edit Rubrik';
$string['default_rubric_name'] = 'Rubrik Tugas';
$string['materialsmanagement'] = 'Manajemen Materi Kuliah';
$string['reviewhistory'] = 'Riwayat Review AI';
$string['aigradingfailed'] = 'Penilaian AI gagal: {$a}';
$string['page'] = 'hal. {$a}';
$string['unknownsource'] = 'Sumber tidak diketahui';
