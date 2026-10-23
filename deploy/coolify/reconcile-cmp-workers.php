<?php
// Run inside Coolify, after the tested image is live. No secrets or resource deletes.
require '/var/www/html/vendor/autoload.php';
$app = require '/var/www/html/bootstrap/app.php';
$app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();
$apply = in_array('--apply', $argv, true);
$target = App\Models\Service::where('uuid', 'avcfd5kwb7cj9r1tx4ygjs6v')->firstOrFail();
if ($target->applications()->where('name', 'web')->count() !== 1) {
    throw new RuntimeException('Expected one stable web runner');
}
$specs = [
    '1uyereuryah2gkppequp4vjn' => ['outbox', '* * * * *'],
    'hhxzn2v587ml3a0tw87xbx79' => ['health', '*/5 * * * *'],
    'qj3p3gksnxr74mvtqofqdm0k' => ['reminders', '0 9 * * *'],
];
Illuminate\Support\Facades\DB::transaction(function () use ($specs, $target, $apply) {
    foreach ($specs as $uuid => [$job, $frequency]) {
        $task = App\Models\ScheduledTask::where('uuid', $uuid)->lockForUpdate()->firstOrFail();
        if ($task->service_id != $target->id && $task->application_id != 4) {
            throw new RuntimeException('Unexpected schedule owner; refusing mutation');
        }
        $changes = ['service_id' => $target->id, 'application_id' => null,
            'container' => 'web', 'command' => "python manage.py run_cmp_job $job",
            'frequency' => $frequency, 'enabled' => true, 'timeout' => 300];
        if ($apply) { $task->update($changes); }
        echo json_encode(['task' => $uuid, 'job' => $job, 'frequency' => $frequency,
            'timezone' => 'UTC', 'applied' => $apply]).PHP_EOL;
    }
});
