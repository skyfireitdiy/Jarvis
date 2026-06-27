/*
 * 误报测试：硬编码凭证 - password变量名但非密码值
 * 漏洞类型：hardcoded_credentials
 * 说明：变量名包含password/key/secret但实际不是密码值，
 *       不应被误报为硬编码凭证
 * 预期：不应检测到hardcoded_credentials
 */

/* 以下变量名包含敏感关键词，但值不是密码 */
int password_min_length = 8;      /* 密码最小长度，不是密码 */
int password_max_retries = 3;     /* 最大重试次数，不是密码 */
int secret_key_length = 32;      /* 密钥长度，不是密钥本身 */
int access_token_timeout = 3600; /* token超时时间，不是token */

void configure() {
    /* 配置参数，不是凭证 */
    int passphrase_min_words = 4;  /* 最小词数，不是密码短语 */
    int api_key_version = 2;       /* API版本号，不是API密钥 */
}
