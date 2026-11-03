"""SNS email, isolated by owner AND verified email address; never the admin topic."""
from datetime import datetime, timezone
import hashlib
import secrets
from urllib.parse import urlsplit
from .errors import HubError

TEXT = {
 'en': ['Environment deadline approaching', 'Renewal completed', 'Automatic renewal declined', 'Renewal recorded; schedule needs attention', 'Environment', 'Deadline (UTC)', 'Next-period estimate', 'Cumulative forecast', 'Ending policy', 'Review environment and renewal', 'Forecasts are not AWS invoices. Renewing requires the existing confirmation flow.', 'At the time of this notice', 'Keep data while paused', 'Back up, then retire resources'],
 'vi': ['Môi trường sắp đến hạn', 'Gia hạn đã hoàn tất', 'Không thể tự động gia hạn', 'Đã ghi nhận gia hạn; lịch cần được đồng bộ', 'Môi trường', 'Thời hạn (UTC)', 'Dự toán kỳ tiếp theo', 'Dự toán cộng dồn', 'Chính sách kết thúc', 'Xem môi trường và dự toán gia hạn', 'Dự toán không phải hóa đơn AWS. Gia hạn vẫn qua luồng xác nhận hiện có.', 'Tại thời điểm thông báo', 'Tạm dừng và giữ dữ liệu', 'Sao lưu rồi thu hồi tài nguyên'],
 'ja': ['環境の期限が近づいています', '更新が完了しました', '自動更新できませんでした', '更新は記録済みです。スケジュールの同期が必要です', '環境', '期限（UTC）', '次の期間の見積もり', '累積見積もり', '終了時の方針', '環境と更新見積もりを確認', '見積もりはAWSの請求額ではありません。更新には既存の確認手順が必要です。', '通知作成時点', '一時停止してデータを保持', 'バックアップ後にリソースを解放'],
 'ko': ['환경 종료 시점이 다가옵니다', '연장이 완료되었습니다', '자동 연장을 진행할 수 없습니다', '연장이 기록되었습니다. 일정 동기화가 필요합니다', '환경', '종료 시점(UTC)', '다음 기간 예상 비용', '누적 예상 비용', '종료 정책', '환경과 연장 예상 비용 확인', '예상 비용은 AWS 청구 금액이 아닙니다. 연장에는 기존 확인 절차가 필요합니다.', '알림 작성 시점', '일시 중지하고 데이터 유지', '백업 후 리소스 회수'],
 'zh-Hans': ['环境即将到期', '续期已完成', '无法自动续期', '续期已记录；计划需要同步', '环境', '截止时间（UTC）', '下一周期预估费用', '累计预估费用', '结束策略', '查看环境和续期预估', '预估不是AWS账单。续期仍需经过现有确认流程。', '通知生成时', '暂停并保留数据', '备份后回收资源'],
 'fr': ['Échéance de l’environnement proche', 'Renouvellement terminé', 'Renouvellement automatique refusé', 'Renouvellement enregistré ; synchronisation requise', 'Environnement', 'Échéance (UTC)', 'Estimation de la période suivante', 'Estimation cumulée', 'Politique de fin', 'Voir l’environnement et le renouvellement', 'Les estimations ne sont pas des factures AWS. Le renouvellement suit la confirmation habituelle.', 'Au moment de cette notification', 'Suspendre et conserver les données', 'Sauvegarder puis libérer les ressources'],
 'de': ['Die Umgebungsfrist endet bald', 'Verlängerung abgeschlossen', 'Automatische Verlängerung abgelehnt', 'Verlängerung erfasst; Zeitplan muss synchronisiert werden', 'Umgebung', 'Frist (UTC)', 'Schätzung für den nächsten Zeitraum', 'Kumulierte Kostenschätzung', 'Beendigungsrichtlinie', 'Umgebung und Verlängerung prüfen', 'Schätzungen sind keine AWS-Rechnungen. Eine Verlängerung erfordert den bestehenden Bestätigungsablauf.', 'Zum Zeitpunkt dieser Mitteilung', 'Pausieren und Daten behalten', 'Sichern und Ressourcen freigeben'],
 'es': ['Se acerca el vencimiento del entorno', 'Renovación completada', 'Renovación automática rechazada', 'Renovación registrada; falta sincronizar la programación', 'Entorno', 'Vencimiento (UTC)', 'Estimación del próximo período', 'Estimación acumulada', 'Política de finalización', 'Ver el entorno y la renovación', 'Las estimaciones no son facturas de AWS. Renovar requiere el proceso de confirmación existente.', 'En el momento de este aviso', 'Pausar y conservar los datos', 'Crear copia y retirar recursos']}
TITLES = {'EXPIRY_SOON': 0, 'RENEWAL_SUCCEEDED': 1, 'RENEWAL_BLOCKED': 2, 'RENEWAL_SYNC_PENDING': 3}
MAINTENANCE_TEXT={
 'en':['CloudHub maintenance notice','Planned start (UTC)','Expected end (UTC)','Impact','This notice does not stop your environment or change its data policy. Check the website for updates.'],
 'vi':['Thông báo bảo trì CloudHub','Bắt đầu dự kiến (UTC)','Kết thúc dự kiến (UTC)','Ảnh hưởng','Thông báo này không tự dừng môi trường hoặc đổi chính sách dữ liệu. Xem website để cập nhật.'],
 'ja':['CloudHubメンテナンスのお知らせ','開始予定（UTC）','終了予定（UTC）','影響','この通知は環境の停止やデータ方針の変更を行いません。更新はウェブサイトで確認してください。'],
 'ko':['CloudHub 유지보수 안내','예정 시작(UTC)','예상 종료(UTC)','영향','이 알림은 환경을 중지하거나 데이터 정책을 변경하지 않습니다. 웹사이트에서 최신 정보를 확인하세요.'],
 'zh-Hans':['CloudHub维护通知','计划开始（UTC）','预计结束（UTC）','影响','此通知不会停止环境或更改数据策略。请在网站查看更新。'],
 'fr':['Maintenance de CloudHub','Début prévu (UTC)','Fin estimée (UTC)','Impact','Cet avis ne suspend pas votre environnement et ne modifie pas la politique des données. Consultez le site pour les mises à jour.'],
 'de':['CloudHub-Wartungshinweis','Geplanter Beginn (UTC)','Voraussichtliches Ende (UTC)','Auswirkungen','Dieser Hinweis stoppt keine Umgebung und ändert keine Datenrichtlinie. Aktualisierungen finden Sie auf der Website.'],
 'es':['Aviso de mantenimiento de CloudHub','Inicio previsto (UTC)','Fin estimado (UTC)','Impacto','Este aviso no detiene el entorno ni cambia la política de datos. Consulta las actualizaciones en el sitio.']}


def compose(row, locale, origin):
    text = TEXT.get(locale, TEXT['en'])
    stamp = lambda value: datetime.fromtimestamp(value, timezone.utc).isoformat() if value else '—'
    if row['type']=='MAINTENANCE_NOTICE':
        labels=MAINTENANCE_TEXT.get(locale,MAINTENANCE_TEXT['en'])
        return 'CloudHub: maintenance notice','\n'.join([labels[0],row['title'],'',row['message'],'',
            labels[1]+': '+stamp(row['starts_at']),labels[2]+': '+stamp(row['ends_at']),labels[3]+': '+row['impact'],
            '',labels[4],origin.rstrip('/')+'/maintenance.html','Notification ID: '+row['notification_id']])
    amount = lambda value: '—' if value is None else f'{value / 1000:.3f} USD'
    lines = [text[TITLES.get(row['type'], 0)], '',
             text[4] + ': ' + row['environment_id'], 'AWS Region: ' + row.get('region', '—'),
             text[5] + ': ' + stamp(row.get('deadline')),
             text[6] + ': ' + amount(row.get('period_estimate_milliusd')),
             text[7] + ': ' + amount(row.get('cumulative_milliusd')),
             text[8] + ': ' + text[12 if row.get('ending_policy') == 'PAUSE' else 13],
             text[11] + ': ' + stamp(row.get('created_at'))]
    if row.get('code'):
        lines.append('Support: ' + row['code'])
    lines += ['', text[9] + ': ' + origin.rstrip('/') + '/#environments-section', '', text[10],
              'Notification ID: ' + row['notification_id']]
    # ASCII subject avoids legacy mail-client encoding problems; body is UTF-8.
    subject = 'CloudHub: ' + ['environment deadline', 'renewal completed', 'renewal declined', 'schedule attention'][TITLES.get(row['type'], 0)]
    return subject, '\n'.join(lines)


class SnsEmail:
    def __init__(self, client, account, region, prefix, origin):
        parsed = urlsplit(origin)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.port not in (None, 443) or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
            raise ValueError('An explicit public HTTPS frontend origin is required')
        import re
        if not re.fullmatch(r'\d{12}', account) or not re.fullmatch(r'[a-z][a-z0-9-]{2,70}', prefix):
            raise ValueError('Scoped account and topic prefix required')
        self.client, self.account, self.region, self.prefix, self.origin = client, account, region, prefix, origin.rstrip('/')

    def token(self):
        return secrets.token_hex(12)

    def topic(self, owner, address):
        suffix = hashlib.sha256((owner + '\n' + address.lower()).encode()).hexdigest()[:40]
        return self.prefix + suffix

    def arn(self, owner, address):
        return f'arn:aws:sns:{self.region}:{self.account}:{self.topic(owner, address)}'

    def check(self, owner, address):
        arn = self.arn(owner, address)
        subscriptions = []
        args = {'TopicArn': arn}
        try:
            for _ in range(3):
                result = self.client.list_subscriptions_by_topic(**args)
                subscriptions.extend(result.get('Subscriptions', []))
                if not result.get('NextToken'):
                    break
                args['NextToken'] = result['NextToken']
            else:
                raise HubError('NOTIFICATION_TOPIC_UNSAFE', 'Unexpected subscription inventory.', 409)
        except self.client.exceptions.NotFoundException:
            subscriptions = []
        # Each owner/address topic must have exactly the expected endpoint only.
        if any(s.get('Protocol') != 'email' or s.get('Endpoint', '').lower() != address.lower()
               or s.get('TopicArn') != arn for s in subscriptions) or len(subscriptions) > 1:
            raise HubError('NOTIFICATION_TOPIC_UNSAFE', 'Unexpected subscription inventory.', 409)
        confirmed = bool(subscriptions and subscriptions[0].get('SubscriptionArn', '').startswith(arn + ':'))
        return {'email_status': 'CONFIRMED' if confirmed else 'PENDING_CONFIRMATION' if subscriptions else 'NOT_SUBSCRIBED',
                'topic_arn': arn, 'masked_email': address[0] + '***@' + address.rsplit('@', 1)[-1]}

    def configure(self, owner, address, allow_subscribe=True):
        name = self.topic(owner, address)
        result = self.client.create_topic(Name=name, Tags=[{'Key': 'cloudhub:managed', 'Value': 'true'},
                {'Key': 'cloudhub:purpose', 'Value': 'user-notifications'}])
        if result.get('TopicArn') != self.arn(owner, address):
            raise HubError('NOTIFICATION_TOPIC_UNSAFE', 'Topic does not match configured account and Region.', 409)
        state = self.check(owner, address)
        if state['email_status'] == 'NOT_SUBSCRIBED' and allow_subscribe:
            self.client.subscribe(TopicArn=state['topic_arn'], Protocol='email', Endpoint=address, ReturnSubscriptionArn=True)
            state['email_status'] = 'PENDING_CONFIRMATION'
        return state

    def send(self, owner, address, row, locale, still_current):
        state = self.check(owner, address)
        if state['email_status'] != 'CONFIRMED':
            return {'email_status': 'PENDING'}  # Confirmation is checked by the next sweep.
        if not still_current():
            return {'email_status': 'SKIPPED_STALE'}
        subject, body = compose(row, locale, self.origin)
        result = self.client.publish(TopicArn=state['topic_arn'], Subject=subject, Message=body)
        return {'email_status': 'PUBLISHED', 'email_message_id': result.get('MessageId')}


def runtime_gateway():
    import os
    if os.getenv('USER_NOTIFICATION_EMAIL_ENABLED', 'false').lower() != 'true':
        return None
    import boto3
    from botocore.config import Config
    return SnsEmail(boto3.client('sns', config=Config(connect_timeout=.4, read_timeout=1,
                    retries={'total_max_attempts': 1})), os.environ['NOTIFICATION_ACCOUNT_ID'],
                    os.environ['AWS_REGION'], os.environ['USER_NOTIFICATION_TOPIC_PREFIX'],
                    os.environ['NOTIFICATION_FRONTEND_ORIGIN'])
