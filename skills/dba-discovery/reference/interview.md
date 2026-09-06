# Interview questions for the platform owner

The server cannot answer these. Ask them in one sitting, write the answers down as given, and quote them on the page under `interview.<topic>`. An answer of "I do not know" is recorded as an unknown with the person who might know.

## interview.backup

Which tool takes the backups (pg_dump, pgBackRest, Barman, mysqldump, mariabackup, xtrabackup, cloud snapshots)? On what schedule? Where are the copies kept, and is at least one copy off the host and off the account that owns the server? What is the retention period? When was a restore last performed end to end, by whom, and how long did it take? Is the restore procedure written down, and where?

## interview.recovery_objectives

If the primary is lost at 2 pm on a weekday, how long may the service be down (recovery time objective)? How much committed data may be lost (recovery point objective)? Who decided those numbers, and when were they last reviewed? Has a failover been exercised in the last year?

## interview.change

How does a schema change get from a developer to production? Which tool applies it? Who reviews it? Is there a change window, and how are emergency changes handled? Who has DDL rights in production?

## interview.access

Who holds the superuser or root password, and where is it stored? Do people log in with personal accounts or a shared one? How is an account removed when someone leaves? Which applications connect, and does each have its own account?

## interview.monitoring

Where do the server logs go and who looks at them? Which monitoring system watches this platform, and which alerts exist (disk, replication lag, connections, long transactions)? Who is on call, and how is an alert escalated at night?

## interview.cost

What does this platform cost per month (hosting or instance size, storage, licences, managed service tier, support contract)? Which line has grown the most in the last year? Is there capacity headroom the business is paying for but not using?

## interview.pain

What breaks most often? What does the team avoid touching? Which report or job is slowest? What would you fix first if you had a week?

## interview.ownership

Who is the business owner (decides priorities and accepts risk) and who is the technical owner (does the work)? Which applications and teams depend on this platform? Is there a contract or compliance requirement (retention, encryption, audit) that applies?
