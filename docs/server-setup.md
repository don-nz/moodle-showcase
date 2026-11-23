# Server setup guide

How to build the showcase from scratch: a Moodle server and a quiz tool server, both reached
through Cloudflare Tunnels. The same steps work on VMs on your PC and on servers from a
hosting provider.

```
 Browser ──https──▶ Cloudflare ──tunnel──▶ Moodle server  (nginx on 127.0.0.1:80)
                         │
                         └──────tunnel──▶ Tool server    (quiz tool on 127.0.0.1:8000)
```

- Neither server opens any web ports. Each server's `cloudflared` connects out to
  Cloudflare, and Cloudflare provides the HTTPS certificates.
- Moodle and the tool talk to each other through their public addresses, the same way a
  college's Moodle would.

The examples use `moodle.aht-test.site` and `tools.aht-test.site`. Keep to one level under
your domain: Cloudflare's free certificate covers `*.aht-test.site`, but not
`moodle.dev.aht-test.site`.

---

## 1. Create the two servers

| | Moodle | Tool |
|---|---|---|
| OS | **Ubuntu Server 24.04 LTS** (required: Moodle 5.3 can't use 26.04's PHP 8.5) | Ubuntu Server 24.04 or 26.04 |
| CPU / RAM / disk | 2 / 4 GB / 25 GB | 1–2 / 2 GB / 15 GB |
| Hostname | `moodle` | `tools` |

**On your PC (virt-manager):**
- Create each VM from the 24.04 Server ISO, on the default NAT network. No IP pinning is
  needed, because the tunnels connect out.
- In the installer, tick **OpenSSH server**.
- Take a snapshot after the install.

**At a hosting provider:**
- Create two Ubuntu 24.04 servers, and add your SSH key while creating them.
- If the provider has its own firewall, allow only SSH (port 22) in.

## 2. SSH from the laptop

1. Copy your laptop's SSH key to each server, so `deploy.sh` and `scp` don't need passwords:
   ```sh
   ssh-copy-id don@<server address>
   ```
2. Add both servers to `~/.ssh/config` on the laptop, so they have short names. For VMs on
   the PC, the laptop reaches them through the PC (`ProxyJump`):
   ```
   Host aht-moodle
       HostName 192.168.122.x      # the VM's IP on the PC (provider: its public IP)
       User don
       ProxyJump don@your-pc       # leave this out for a provider
   Host aht-tools
       HostName 192.168.122.y
       User don
       ProxyJump don@your-pc
   ```
3. To find a VM's IP, run `sudo virsh net-dhcp-leases default` on the PC.

## 3. Create the Cloudflare tunnels

In the Cloudflare dashboard, go to **Zero Trust → Networks → Tunnels**. Cloudflare renames
things now and then, so the labels may differ slightly.

1. **Create a tunnel**, choose **Cloudflared**, and name it `showcase-moodle`.
2. The install page shows a command ending in a long **token**. Copy just the token, and
   don't run the command; the setup script does that.
3. Add a public hostname (published application):
   - **Subdomain:** `moodle`
   - **Domain:** `aht-test.site`
   - **Service:** `HTTP`, URL `localhost:80`
4. Repeat for `showcase-tools`, with subdomain `tools` and service `HTTP`, URL `localhost:8000`.

**Keep Cloudflare's security features off these two hostnames.** Moodle and the tool call
each other without a browser, so a challenge page breaks grade return and content selection:
- No **Cloudflare Access** application on them.
- **Bot Fight Mode** off, or a WAF rule that skips bot checks for these two hostnames.
- No "I'm under attack" mode.

Keep the tokens private: anyone with a token can run that tunnel.

## 4. Set up the Moodle server

From the laptop:
```sh
scp deploy/setup-moodle.sh aht-moodle:
ssh aht-moodle
sudo MOODLE_URL=https://moodle.aht-test.site ADMIN_EMAIL=you@example.com bash setup-moodle.sh
```
- Paste the `showcase-moodle` token when it asks.
- The script takes about 10 minutes.
- At the end, show the generated admin password with `sudo cat /root/moodle-credentials`, and
  store it in your password manager.

## 5. Set up the tool server

From the laptop:
```sh
scp deploy/setup-tools.sh aht-tools:
ssh aht-tools
sudo TOOL_URL=https://tools.aht-test.site MOODLE_URL=https://moodle.aht-test.site bash setup-tools.sh
exit
deploy/deploy.sh aht-tools        # installs the code; should end with "active"
```
Paste the `showcase-tools` token when it asks.

## 6. Check both are reachable

- https://tools.aht-test.site/.well-known/jwks.json shows `{"keys":[...`.
- https://moodle.aht-test.site shows the Moodle login page with a padlock.
- In Cloudflare, both tunnels show as **Healthy**.

## 7. Connect the tool to Moodle

Log in to Moodle as `admin`, then:

1. Go to **Site administration → Plugins → Activity modules → External tool → Manage tools**.
2. In **Tool URL**, enter `https://tools.aht-test.site/lti/register` and click
   **Add LTI Advantage**. When the dialog closes, click **Activate**.
3. Click the **pencil** on the tool and check these settings:
   - **Tool configuration usage:** *Show in activity chooser and as a preconfigured tool*
   - **Default launch container:** *Embed, without blocks*
   - **Supports Deep Linking:** ticked, with **Content Selection URL**
     `https://tools.aht-test.site/lti/launch`. Registration should already have set this.
   - **IMS LTI Assignment and Grade Services:** *Use this service for grade sync only*
   - **Accept grades from the tool:** *Always*
   - **Share launcher's name with tool:** *Always*
4. Save.

Unlike the old laptop setup, you don't need to change Moodle's cURL blocked hosts list,
because both servers now use public addresses.

## 8. Users and courses

1. Create accounts under **Site administration → Users → Add a new user**: a test student,
   and one account per teacher.
2. Build the two courses from [showcase-course.md](showcase-course.md).
3. Enrol everyone under **Participants → Enrol users**: teachers as **Teacher** in their own
   subject's course, and the test student as **Student** in both.

## 9. Test from outside

On your phone with Wi-Fi off:
1. Log in as the test student and finish a quiz. Check that the green "sent to the Moodle
   gradebook" note appears.
2. Log in as admin and check the score in that course's **Grades**.

---

## Looking after it

- **Security updates** install automatically (`unattended-upgrades`).
- **Moodle updates.** On the Moodle server:
  ```sh
  cd /var/www/moodle && sudo git pull
  sudo -u www-data php admin/cli/upgrade.php --non-interactive
  ```
- **New or fixed quizzes.** On the laptop, run `python3 scripts/build_content.py`, then
  `deploy/deploy.sh aht-tools`.
- **Backups:**
  - VM snapshots on the PC, or the provider's backup option.
  - For Moodle on its own: **Course → More → Course reuse → Backup**, without users, gives a
    `.mbz` file you can restore anywhere.

## Moving to a hosting provider later

1. Repeat steps 1–7 on the new servers. You can reuse the same tunnels: run
   `sudo cloudflared service install <token>` on the new servers, then stop the old ones.
2. Move the courses with course backup and restore. The activities point at the tool, so if
   the tool's address stays the same they keep working. Otherwise re-pick each one with
   **Select content**.
