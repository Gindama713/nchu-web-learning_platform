# 中央处理器课程学习系统接口契约

版本0.6，需求设计已完成团队评审；所有路径为设计，尚无运行服务。接口统一前缀 /api/v1。模块编号、实验逻辑及判分以PRD为准，持久化以DBD为准。

## 1 公共协议

使用HTTPS及UTF-8 JSON；上传用multipart/form-data。成功响应为 data（对象/数组）和request_id；分页额外返回page、page_size、total。错误响应为error对象（code、message、details）和request_id，details只含可公开字段，不含堆栈、路径、密钥或隐藏测试。创建资源返回201，异步任务202，读取/更新200，删除204。ID均为正整数，时间为带Z的ISO 8601 UTC字符串，显示时转换到上海时区。分页page默认1、page_size默认20且最多100，列表只允许文档列出的筛选项。

鉴权采用服务端会话和HttpOnly/Secure/SameSite=Lax Cookie（仅README规定的本机HTTP开发关闭Secure），同源访问；所有写请求除首次注册/登录外携带X-CSRF-Token并验证Origin。注册/登录同样验证同源来源并限流。会话闲置2小时失效，登出/停用立即撤销。GET /auth/session返回本人身份和会话绑定csrf_token，不返回会话密钥。公开注册的role固定student。新增语义码STATE_MISMATCH、ACTION_NOT_UNDOABLE映射422，INDEX_UNAVAILABLE、SEARCH_LIMIT映射503；模块字段见各业务节，幂等细则见第11节。

下文S=学生，T=任课教师，A=管理员，L=已登录且有该课程访问权。T不是任意教师；S写入的user_id永远从会话取。所有按ID访问都验证对象和课程归属。不可见对象统一404；已知可见对象但无操作权限返回403。服务端不接收客户端分数、角色、文件路径、评测状态作为可信值。

| HTTP | 错误码 | 触发条件 |
|---|---|---|
| 400 | VALIDATION_ERROR | 类型、范围、未知写字段、格式或必需字段错误 |
| 401 | UNAUTHENTICATED | 未登录、会话失效、账号停用 |
| 403 | FORBIDDEN / CSRF_FAILED | 权限或CSRF不满足 |
| 404 | NOT_FOUND | 对象不存在或对当前用户不可见 |
| 409 | REVISION_CONFLICT / STATE_CONFLICT / IDEMPOTENCY_CONFLICT / DUPLICATE | 修订冲突、状态不允许、同键不同请求、唯一项冲突；RESOURCE_IN_USE、QUESTION_RESERVED、QUIZ_NOT_PUBLISHED、EVENT_CONFLICT也使用409 |
| 413 | FILE_TOO_LARGE | 上传超出类型限定 |
| 415 | UNSUPPORTED_MEDIA | 文件类型/内容不支持；PREVIEW_UNSUPPORTED同为415 |
| 422 | INVALID_CIRCUIT / INFEASIBLE_CONSTRAINTS / WIRING_INVALID / INVALID_SCORE / INVALID_ATTENDANCE_CODE | 电路、组卷、接线、人工评分或签到码语义无效 |
| 429 | RATE_LIMITED | 频率或个人活动任务超限，返回Retry-After秒数 |
| 503 | GRADER_UNAVAILABLE / QUEUE_FULL / DB_BUSY / MAINTENANCE | 服务未就绪、队列满、有限重试后数据库忙或维护模式拒绝普通写入 |
| 500 | INTERNAL_ERROR | 非预期服务错误，记录request_id供排查 |

通用查询日期from/to满足from≤to，最长366天；排序仅使用白名单字段。文本名称1—100字符，说明0—5000字符，富文本只保留允许标签/属性。所有列表与detail使用同一字段契约；生成/轮换的一次性secret字段明确例外。分页空结果为200 {data:[],page:请求page,page_size:有效page_size,total:0,request_id}，超出末页返回data:[]且total仍为实际数量；不使用推荐reason枚举。下表参数未标“?”的均为必需，id路径变量均为正整数。

## 2 身份与课程接口 SPEC-001

| 方法与路径 | 入参 | data返回 | 权限与特例 |
|---|---|---|---|
| POST /auth/register | student_no:8—20位字母数字，name:1—50，password:12—128字符 | user:{id,student_no,name,role} | 公开；重复账号409；role字段禁止传入 |
| POST /auth/login | student_no,password | user及csrf_token，并设置Cookie | 公开；错误统一401；每账号/IP均限流 |
| GET /auth/session | 无 | user:{id,name,role},csrf_token,expires_at | 登录 |
| POST /auth/logout | 无 | 204 | 登录及CSRF |
| PATCH /users/me | name?，old_password?，new_password? | 本人user | 登录；改密必须旧密码并撤销其他会话 |
| GET /users | role?，q?，分页 | User列表（无密码哈希） | A |
| PATCH /users/{id} | role?:student/teacher/admin，active?:bool | User | A；角色/状态变更事务结束后必须至少保留一个active管理员（含并发降级），审计 |
| GET /courses | 分页 | Course列表 | 登录；只列成员/授课课程，A可查全部 |
| POST /courses | title,description?,teacher_id | Course:{id,title,description,teacher_id} | A |
| POST /courses/{id}/members | user_id，member_role:student/teacher | Membership | T/A；T不能授予teacher |
| DELETE /courses/{id}/members/{user_id} | 无 | 204 | T/A；保留历史成绩，撤销当前访问 |
| GET /courses/{id}/members | member_role?,q?,分页 | Membership含user_id/name/student_no/member_role/active | T/A；学生不获全班个人资料 |
| GET /users/lookup | student_no:完整学号 | {id,student_no,name,role,active} | T/A；精确查询、每分钟20次、留审计；供添加成员 |
| PATCH /courses/{id} | teacher_id,retain_previous_teacher:bool | Course | A；新负责人为active teacher，同事务建teacher成员；旧负责人留任须显式保留，否则停用其课程成员 |


course表示一个学期的一个教学班。teacher_id仅负责人属性；T权限必须同时满足user.active、user.role=teacher及course_member.active/member_role=teacher，不能以teacher_id单独放行。课程创建同事务创建负责人成员。A可管理课程和人员，但不自动拥有教师业务成绩改写权限。负责人移除/全局降级前先移交其负责课程，否则409；全局降级同事务停用不再合法的课程角色，会话即时重新鉴权。成员删除实际置active=false。

GET /auth/session的expires_at与服务端闲置超时一致。

## 3 教学管理接口 SPEC-002—005

| 方法与路径 | 入参 | data返回 | 权限/业务错误 |
|---|---|---|---|
| POST /courses/{id}/attendance-tasks | title,start_at,late_at,end_at | AttendanceTask:{id,title,start_at,late_at,end_at,status,code_expires_at,code} | T；start≤late≤end且start<end；code仅在本次创建响应一次返回，code_expires_at=end_at |
| GET /courses/{id}/attendance-tasks | status?，分页 | 任务列表，所有角色均不含code/code_hash/扫码令牌 | L |
| POST /attendance-tasks/{id}/check-ins | code:6位数字（扫码也解析为该令牌） | AttendanceRecord:{id,status,checked_at} | S；同人重复返回原记录；窗口外409；错误码422 INVALID_ATTENDANCE_CODE；每分钟5次失败限流 |
| POST /attendance-tasks/{id}/close | 无 | Task及各状态人数 | T；重复关闭返回现态 |
| POST /attendance-tasks/{id}/rotate-code | 无 | {code,expires_at}及教师扫码内容 | T；只在开放窗口内轮换，一次返回明文，原码立即失效 |
| POST /attendance-tasks/{id}/leave-requests | reason:1—500 | Leave:{id,status:pending,reason} | S；同任务同学生仅1项有效申请 |
| PATCH /leave-requests/{id} | status:approved/rejected，note:1—500，restore_status?:present/late/absent | Leave | T；已经关闭时允许审计更正，不覆盖原审批记录 |
| GET /courses/{id}/attendance-records | task_id?，student_id?，分页 | 记录列表 | T全班/S本人；学生student_id仅允许本人 |
| POST /courses/{id}/resources | file，title，kind:slides/video/guide/question_bank，chapter_id? | ResourceVersion:{resource_id,version,id,title,kind,size,sha256} | T；文档20MiB，视频100MiB；question_bank强制teacher_only；导入见本节 |
| POST /resources/{id}/versions | file，change_note | 新ResourceVersion | T；原版本不覆盖 |
| GET /resources/{id}/versions | 分页 | ResourceVersion列表 | L；每个旧版本按资源当前可见性鉴权 |
| GET /courses/{id}/resources | q?，kind?，chapter_id?，分页 | 资源和最新版本 | L；学生排除teacher_only及question_bank |
| GET /resource-versions/{id}/content | intent:view/download，event_id:UUID；Range?请求头 | 二进制流；view为inline、download为attachment | L；按资源当前可见性鉴权；question_bank仅T且只允许download；记录事件规则见下文 |
| POST /courses/{id}/preparations | title,knowledge_ids:ID[],resource_version_ids:ID[],question_version_ids:ID[],quiz_ids:ID[],scheduled_at? | Preparation:{id,...入参,status:draft} | T；关联对象同课程 |
| POST /preparations/{id}/copy | title | 新Preparation（含quiz_ids） | T；复制关联，不修改源；不复制或自动发布试卷 |
| POST /preparations/{id}/publish | replaces_id? | Preparation及published_at | T；发布draft；若replaces_id指定同课程published旧备课，同事务将旧项置withdrawn并发布新项，生成通知 |
| POST /preparations/{id}/withdraw | reason:1—500 | Preparation(status=withdrawn,withdrawn_at) | T；重复撤回返回现态；历史关联保留 |
| GET /courses/{id}/preparations | 分页 | Preparation列表 | T全部/S仅已发布 |
| GET /notifications | unread?，分页 | {id,title,target_type,target_id,read_at}列表 | 登录，本人 |
| PATCH /notifications/{id} | read:true | 通知 | 本人 |
| GET /courses/{id}/chapters | 分页 | {id,title,position}列表及chapters_revision | L；position升序，学生仅含已发布知识点的章节 |
| POST /courses/{id}/chapters | title | Chapter:{id,title,position}及chapters_revision | T；追加到末尾，同事务递增课程chapters_revision |
| PATCH /chapters/{id} | title | Chapter | T；名称1—100字符，不改变排序 |
| PUT /courses/{id}/chapter-order | chapters_revision,chapter_ids:完整有序ID数组 | {chapters_revision,items:[{id,title,position}]} | T；数组须恰含本课全部章节且不重复；过期409，非法集合400；原子重排position=0至n−1 |
| POST /chapters/{id}/knowledge-points | title,content,example?,published:bool,is_foundational?:bool默认false | Knowledge:{id,chapter_id,title,content,example,published} | T |
| PATCH /knowledge-points/{id} | title?,content?,example?,published?,is_foundational? | Knowledge | T；变更触发索引版本更新 |
| GET /courses/{id}/knowledge-points | q?，chapter_id?，分页 | Knowledge列表 | L，学生只看已发布 |
| GET /knowledge-points/{id} | 无 | Knowledge及is_bookmarked、progress | L |
| PUT /knowledge-points/{id}/bookmark | bookmarked:bool | {bookmarked} | S；幂等 |
| PUT /knowledge-points/{id}/progress | completed:bool | {completed,updated_at} | S；该状态只代表学习进度自报 |
| GET /courses/{id}/leave-requests | task_id?,status?,分页 | Leave列表 | T班级/S本人；业务规则见第3节考勤审批；空结果见第1节分页 |
| PUT /leave-requests/{id} | reason | Leave | 本人S；pending可改、rejected可重提pending，保留审批历史；approved不可改；仅end_at前 |
| PATCH /attendance-records/{id} | status:present/late/leave/absent,reason | Record | T；更正写审计和本人通知，不伪造checked_at |
| POST /resources/{id}/question-imports | resource_version_id；Idempotency-Key | {import_id,question_version_ids,count} | T；仅question_bank；UTF-8 JSON数组，最多500题，每题为Question模型；全量校验后同事务创建，错误返回400及题目下标；禁止部分导入 |
| PATCH /resources/{id} | title?,visibility:students/teacher_only | Resource | T；question_bank不能设students；事务检查所有published备课引用；存在时409 RESOURCE_IN_USE及阻塞备课ID；先撤回所有引用备课或发布不再引用该资源的替代备课 |
| GET /preparations/{id} | 无 | Preparation含knowledge_ids/resource_version_ids/question_version_ids/quiz_ids及状态 | T全部/S已发布 |
| PATCH /preparations/{id} | title?,knowledge_ids?,resource_version_ids?,question_version_ids?,quiz_ids?,scheduled_at? | Preparation | T；仅draft；数组传入代表整体替换 |

资源访问契约：content的intent必传，不猜测浏览器是否保存文件；服务端固定event_type映射view→view、download→download，不能由第二个写请求自行上报事件。前端每次明确打开预览/下载生成一个event_id，重试及视频/PDF Range分片复用同ID。授权通过且准备发送非空内容的200/206时首次记录事件；401/403/404/415/416、HEAD及304不计数。UQ(user_id,event_id)防重试/分片重复计数，复用ID但version或intent不同409 EVENT_CONFLICT；同ID同对象只记录一次并允许继续取分片。事件仅代表成功提供内容，不证明学生读完或保存完成；不做“使用时长”推断。view仅允许受支持的PDF、PNG/JPEG、视频类型，其他类型415 PREVIEW_UNSUPPORTED并提示显式download；不内联HTML/脚本/题库JSON。两种intent都经过同一业务权限检查及文件名清洗，不暴露存储路径。

备课随堂测关联：quiz_id等于paper.id，quiz_ids非重复ID数组，允许[]。draft可引用本课程kind=quiz的draft/published试卷；发布备课时关联测验必须published，否则409 QUIZ_NOT_PUBLISHED，不能因备课发布自动发布测验。关联只提供已有测验入口，测验试题、参与名单、窗口及讲评仍由SPEC-008负责。备课复制保留quiz_ids供教师修改；发布后关联冻结，换测验须复制并替代旧备课。学生备课详情的quiz_ids只含本人有参与权限的关联，另返回quizzes数组，每项为测验元数据{id,title,window_state,start_at,end_at}，无权关联项不返回；开始前不含题干，答案必须经原测验接口按讲评权限读取。所有关联同课程校验，不能绕过测验时间/答案保护规则。

Resource增加visibility，普通资源默认students，题库源文件永久teacher_only。备课status=draft/published/withdrawn，withdrawn终态且不能重新发布；copy可从任意状态创建新draft。撤回只取消学生可见性，历史关联、通知和审计不删除，旧通知点击返回404。替代关系replaces_id只能指向同课程published旧项且不能自指；并发替代以条件更新避免双重成功。收紧资源权限与备课发布/撤回使用同一数据库短写事务串行校验，所有旧文件版本立即按新权限鉴权；已下载到学生本机的内容无法追回。备课发布只允许students资源、已发布知识点和practice_available=true的客观题固定版本；学生仍不获得answer/explanation，提交练习后按规则显示。题库导入文件无独立公开URL；file_object仅存储，不是授权入口。所有下载先由所属业务对象判权，包括旧版本和备课跳转。

签到与请假：批准请假替换该人的有效考勤状态并留原值审计；pending不改变签到，批准后签到返回原leave记录。关闭时冻结名单未有有效记录者补absent；拒绝已批准请假属于更正，教师必须显式选择恢复状态，不猜测出勤。关闭后学生不能重提，教师可更正并通知。

GET /courses/{id}/chapters提供分页{id,title,position}，排序position升序并返回chapters_revision；权限L，学生只列含已发布知识点的章节，教师可看空章节。GET /resources/{id}/versions提供分页ResourceVersion，按当前资源权限鉴权。

签到码公开模型：AttendanceTask查询/关闭响应仅含id/course_id/title/start_at/late_at/end_at/status/code_expires_at，不含code或code_hash；创建响应额外含一次性code（6位字符串，保留前导0），轮换响应含code/expires_at/扫码内容，均Cache-Control: no-store。DBD只存哈希，不保存明文到日志、通知或幂等响应缓存。教师刷新或忘记码时通过轮换获得新码，原码立即失效；关闭后不得轮换。没有“找回旧码”界面或查询接口。R40按PRD SPEC-002 AC-05验收。旧码失败用尚未签到学生验证，已成功签到者重复请求仍返回原记录，不能据此判断码是否有效；错误明文不回显。

## 4 习题课堂接口 SPEC-006—008

Question写模型：type枚举single/multiple/boolean/numeric/short，stem非空，options为有序{key,text}数组（选择题2—8项），answer与学生value的类型按下表严格区分，tolerance为数值题非负容差默认0，explanation为文本，difficulty取easy/medium/hard，knowledge_ids非空ID数组，practice_available为布尔且默认false。学生读取版本始终删除answer/explanation，允许讲评后才返回。题目编辑产生版本，已发布试卷引用旧版本。

| type | 标准answer | 学生value | 校验与判分 |
|---|---|---|---|
| single | 一个选项key字符串 | 一个选项key字符串 | key必须存在，相同满分 |
| multiple | 非空、不重复key数组 | 不重复key数组，允许[]表示未答 | 每个key须存在；集合完全相同满分，否则0 |
| boolean | JSON布尔 | JSON布尔 | 不接受0/1或字符串 |
| numeric | 有限JSON数值 | 有限JSON数值 | abs(value-answer)≤tolerance满分；禁止NaN/Infinity |
| short | 1—5000字符参考文本 | 1—5000字符文本，去首尾空白 | 非空作答人工评分，不做字符串自动匹配 |

非选择题options必须[]，选择题key唯一且1—20字符；numeric之外tolerance必须0。提交省略题目、value=null、multiple=[]、short空白均标准化为未答，得0；标准answer不可为空。其他类型错误/未知key/重复key或题号400，整份提交拒绝且不产生部分答卷。分数/配分为非负有限JSON数值且最多两位小数，内部精确转换百分之一分；配分必须>0，不静默四舍五入请求值。

Attempt统一读模型：{id,paper_id,student_id,revision,status,score,partial_score,total_points,submitted_at,answers:[{question_version_id,value,answered,grading_status,score,max_score,comment,correct,answer?,explanation?}]}。revision初始0；status=partial/graded；grading_status=unanswered/pending/graded；pending的score、correct均null，客观题已评分correct为布尔（漏答false），简答correct始终null。score字段始终存在，部分批阅时null。学生只在允许讲评时获得标准answer/explanation，教师可读取；这里的学生value与标准answer不可混用。

manual-scores仅允许非空items，题号唯一、属于本卷且为已作答简答；每题0≤score≤max_score，comment为0—1000字符。整批先校验，类型/重复/精度错误全批400；分值超配分、非本卷或非可批简答全批422；均不更改revision；revision冲突409。成功同事务评分、汇总、审计并revision+1，返回完整Attempt；允许更正已批简答，保留前后分及操作者，不允许批改客观题或漏答0分。
| 方法与路径 | 入参 | 返回 | 权限/特例 |
|---|---|---|---|
| POST /courses/{id}/questions | Question写模型 | {id,version_id,...Question} | T |
| PATCH /questions/{id} | Question待更新字段 | 新题目版本 | T |
| GET /courses/{id}/questions | type?,difficulty?,knowledge_id?,分页 | Question列表（按权限脱敏） | L |
| POST /courses/{id}/papers | title,items:[{question_version_id,points>0}],kind:homework/exam/quiz,confidential?:bool | Paper:{id,title,kind,confidential,total_points,status:draft} | T；题目不得重复 |
| POST /papers/{id}/publish | start_at,end_at,review_at,confidentiality_note? | Paper及时间字段 | T；start<end≤review；发布后题目冻结 |
| GET /papers/{id} | 无 | Paper及脱敏items、start_at、end_at、review_at | L；学生仅已发布且可见 |
| POST /papers/{id}/attempts | answers:[{question_version_id,value}]；Idempotency-Key头 | Attempt（完整模型见上） | S；按服务器截止时间；status=partial时score=null并返回partial_score；全批完status=graded |
| GET /attempts/{id} | 无 | 完整Attempt（含revision及按权限脱敏的answers） | 本人/T；review_at前不暴露答案 |
| PATCH /attempts/{id}/manual-scores | revision,items:[{question_version_id,score,comment}] | 完整Attempt含revision | T；仅简答且分数不超配分，审计 |
| GET /users/me/wrong-questions | knowledge_id?，分页 | [{question_id,question_version_id,knowledge_ids,last_attempt_type,last_attempt_id,wrong_count,resolved,answer_visible}]；标准答案仅answer_visible=true时附加 | S |
| POST /questions/{id}/practice-attempts | question_version_id,answer；Idempotency-Key | {attempt_id,question_version_id,correct,score,explanation}（score正确100，否则0） | S；已发布练习题；不得获取未开放考试的答案 |
| POST /courses/{id}/demo-sessions | preset:gate/comb/sequential/alu/memory/cpu,experiment_version_id? | Demo:{id,preset,revision,state,active:true} | T；cpu/alu/sequential可关联已发布实验版本，preset与版本模式核对 |
| PUT /demo-sessions/{id}/state | revision,action:step/reset/pause/run，inputs? | Demo最新revision和寄存器/总线state | T；过期revision返回409 |
| GET /demo-sessions/{id} | after_revision? | Demo当前状态 | L；轮询每1秒，未变更也返回当前revision |
| POST /courses/{id}/quizzes | paper_id,start_at,end_at,confidentiality_note? | Quiz:{id=paper_id,paper_id,status} | T；仅draft quiz试卷，发布后开放 |
| POST /quizzes/{id}/attempts | answers；Idempotency-Key | Attempt | S；复用试卷判分规则，截止409 |
| GET /quizzes/{id}/statistics | 无 | QuizStatistics（下述逐题模型） | T；按有效答卷 |
| POST /quizzes/{id}/review | 无 | {review_published_at} | T；测验关闭后开放讲评 |
| GET /courses/{id}/papers | kind?,status?,分页 | Paper元数据列表 | T全部/S已发布且在参与名单；开始前不含题干 |
| GET /courses/{id}/quizzes | status?,分页 | kind=quiz的Paper元数据 | 同上，quiz_id就是paper_id |
| GET /courses/{id}/attempts | paper_id?,student_id?,status?,分页 | Attempt列表 | T班级/S本人；供历史和待批阅入口 |
| GET /courses/{id}/demo-sessions | active?,分页 | Demo列表 | L；学生可见本课预设演示，若关联实验须已发布 |
| POST /demo-sessions/{id}/close | revision | Demo(active=false) | T；关闭后不可推进，可新建 |

QuizStatistics={quiz_id,source_until,expected_count,submitted_count,missing_count,objective_correct_rate,questions:[{question_version_id,type,max_score,submitted_count,answered_count,unanswered_count,graded_count,pending_count,correct_count,correct_rate,mean_score,options:[{key,text,selected_count,selection_rate}]}]}。按冻结名单及唯一答卷统计，missing=expected−submitted；逐题unanswered=submitted−answered。客观题correct_rate=correct_count/submitted_count（漏答算错），零提交null；objective_correct_rate为所有客观题正确数/(提交数×客观题数)，无分母null；简答correct_count/correct_rate=null。graded_count包括漏答0分，pending_count仅待批简答；mean_score只用已定分，零已定分null。选择题options含每个选项含零计数，selection_rate=selected_count/submitted_count，零提交时null，多选比例和可>1；非选择题options=[]。题目按paper_item.position，选项按题目原顺序；教师专用响应可以看到题干选项，但不输出学生身份列表。
创建quiz复用paper发布的保密资格/并发占用校验，confidential=true时同样要求confidentiality_note；在同一事务中发布对应draft paper，写入start_at/end_at，review_at初始为null表示暂不开放解析，status按服务器时间计算；教师review后写入paper.review_at（响应review_published_at为其别名，不另存）。普通paper发布仍要求非空review_at≥end_at。测验关闭以end_at判断，客户端不能自行宣告已关闭。单选按key相等、多选按选项集合完全相等才得满分，多选不设漏选部分分；判断按布尔相等；数值按绝对误差≤tolerance；简答仅人工评分。题库学生列表仅包含practice_available=true的公开练习题，考试专用题不通过其他入口泄露。


整卷只支持homework/exam/quiz，单题练习的answer请求值沿用第4节学生value规则，返回score为0/100、correct为布尔；单题练习只支持公开客观题，不支持简答单题练习。试卷仅draft/published两种存储状态，响应window_state=upcoming/open/closed由时间计算。开始前只返回标题、配分总额和时间；start≤now<end才允许读题和提交；截止后仍可读已开放题目，review_at未到或为null不返回标准答案/解析。每人每卷只交一次；不同幂等键再次交卷409。漏题按0分记录（包括漏答简答），空数组允许交白卷；重复题号、非本卷版本号或题型值非法400，不能忽略多余答案。简答已作答未批时status=partial、score=null、partial_score为已定分之和；全定分时status=graded、score=partial_score。人工部分批阅维持partial，重复更新须提供attempt.revision防覆盖。

练习请求增加question_version_id，必须属于路径question且已开放；响应含该version_id，防止答题期间题目更新造成错判。错题wrong_count统计该question历次实际作答且错误的客观题记录，简答不自动进入客观错题本；last_attempt_id/type指最近一次错误来源，question_version_id指该来源版本；之后正确练习可将resolved置true，新错答再置false。answer_visible先检查question身份是否仍被保密卷保护；受保护时固定false，其他情况依据来源作答所属试卷review_at或公开练习资格派生，不能只检查题目当前最新版。错题记录需等允许讲评才能返回考试答案，公开题可用于明确不要求保密的测评，但不能因新建版本或改为不公开而恢复保密。paper新增confidential布尔，exam默认true、其他默认false；保密卷发布及组卷排除曾practice_available=true的question及其全部版本，也排除曾进入对学生开放试卷的question。公开题的改编须实质改变题干/条件/答案并新建question，教师在保密发布时提交1—1000字符confidentiality_note确认未公开且非简单复制；系统校验可追踪的公开历史，不能保证识别跨题目复制。题目若被仍受答案保护的已发布保密卷使用，禁止将其任何版本开放练习，亦禁止再发布引用同题目的其他试卷，返回409 QUESTION_RESERVED；保密卷发布也不得与仍受答案保护的已发布卷共享question。答案保护到实际允许讲评时刻为止：published且(review_at=null或now<review_at)即受保护，不能用end_at代替；因此保密测验截止而未讲评时，question身份的所有版本仍不得开放练习/用于其他卷。公开练习创建/更新/作答、备课题目发布、试卷/quiz发布均调用同一保护检查；学生题目列表和答案/解析读取也检查，若历史异常数据已开放则拒绝练习作答及解析读取（409 QUESTION_RESERVED），不得从错题本绕过。自动讲评以服务器now≥review_at为准，quiz显式review事务设review_at=now后才释放保护；所有发布/公开变更在同一短写事务复核，避免并发泄题。

演示preset为内置可信场景：gate为AND/OR/NOT/XOR真值；comb为多路选择/组合ALU；sequential为REG8；alu为ALU8；memory为ROM16X8读取；cpu为CPU-EDU-8固定程序执行。gate/comb/memory无实验关联也可用，禁止任意脚本。场景只读定义固定scene_version，demo_session固化版本和初态；state动作只允许该场景的白名单输入。CPU演示使用可信内置状态机和ROM，不调用学生.circ；circuit-only的EXP-04可关联CPU演示而不要求wiring panel。组合场景step仅重新传播，时序场景按PRD周期推进。教学演示不写学生实验成绩。

## 5 分析与智能接口 SPEC-010—016

| 方法与路径 | 入参 | 返回data | 权限及约束 |
|---|---|---|---|
| GET /courses/{id}/analytics | 二选一：dimension:attendance/knowledge/wiring/grading/resources/scores及from?,to?,student_id?,kind?,paper_id?,performance_paper_ids?；或仅analysis_run_id | {analysis_run_id,dimension,sample_size,metrics,series,algorithm_version,generated_at} | T班级/S本人；首次查询生成并保存不可变快照；按ID读取本人创建的同课程统计快照；无样本metrics相关值为null |
| GET /courses/{id}/analytics/export | analysis_run_id:正整数，format:csv | UTF-8 CSV文件 | T；仅导出本人创建的同课程统计快照，重新鉴权；单元格公式前缀转义，不重新读取事实表计算 |
| POST /courses/{id}/qa | question:1—500，top_k?:1—5默认3 | {matches:[{knowledge_id,excerpt,similarity}],found,reason,index_version,algorithm_version} | L；相似度0—1；无匹配为found=false；参数、reason枚举和排序见PRD第4.3节 |
| GET /courses/{id}/recommendations | limit?:1—20默认5 | {items:[{knowledge_id,question_version_id,reason,score,mastery,sample_size}],reason,source_until,algorithm_version} | S本人；完整算法及空结果枚举见PRD第4.3节 |
| POST /courses/{id}/generated-papers | title,kind:homework/exam/quiz,count:1—100,total_points:1—1000,knowledge_ids,difficulty_counts:{easy,medium,hard},seed?:整数,confidential?:bool（exam默认true，其余false） | {paper_id,selected_version_ids,coverage,seed,algorithm_version} | T；数量和不匹配400；无可行解422 |
| GET /courses/{id}/warnings | from?,to?,status?，分页 | [{id,student_id,reasons,sample_size,status,algorithm_version}] | T；按最新统计批次，数据不足注明 |
| PATCH /warnings/{id} | status:handled，note:1—500 | Warning | T |
| GET /courses/{id}/knowledge-graph | root_id? | {nodes:[{id,title,mastery?}],edges:[{source,target,type}],prerequisite_paths} | L，mastery仅本人或授权范围 |
| POST /courses/{id}/knowledge-edges | source_id,target_id,type:prerequisite/contains | Edge | T；自环、跨课、先修环422 |
| POST /courses/{id}/recognitions | image:PNG/JPEG≤5MiB且≤4096×4096 | {id,status,items:[{symbol,bbox,confidence,confidence_band,label,label_status}],requires_confirmation:true,algorithm_version,template_set_sha256} | L；不支持类型415；无法识别返回status=unrecognized |
| POST /recognitions/{id}/confirm | items:[{symbol,bbox,label?}] | {id,status:confirmed,confirmed_items,algorithm_version,template_set_sha256} | 原提交者；仅生成结构草稿，不执行任意文件 |
| POST /courses/{id}/warning-runs | from?,to?；Idempotency-Key | 201 {analysis_run_id,status:completed,source_until,sample_size,model_status,warning_count} | T；默认最近28天；同步限时计算，失败503不创建半批结果；算法见PRD第4.2节 |
| GET /courses/{id}/warning-runs | 分页 | 批次及model_status列表 | T |


### 5.1 统计维度与返回模型

analytics响应增加source_until、population_basis、warnings和unit；series统一为[{period_start,period_end,metrics}]，区间左闭右开。S限定本人，T默认班级；所有比率为0—1，小数均分保留两位，无分母为null。

统计快照契约：首次按筛选条件查询时，在同一数据库读快照中提取当前有权访问的输入，冻结解析后的from/to、实际对象集合、个人或班级范围、source_until及算法版本；读事务结束后计算，在短写事务中保存analysis_run的输入与完整结果，保存成功才返回200及analysis_run_id。不得只保存截止时间而在导出时重读已更正的事实值。空样本也保存合法快照；失败503不返回可供导出的ID，不写半份快照。保存前再次检查当前身份与课程访问权，已经失效时不交付结果。

前端保存本次analysis_run_id，导出只传该ID和format=csv；export不得同时传dimension/from/to/student_id等筛选项，混用400。刷新统计按新筛选查询生成新快照；若要恢复原页面，仅传analysis_run_id读取原结果，不能混用新筛选或静默重算。CSV的字段、分母、排序及展示精度按所引用快照的结果生成，并标明analysis_run_id、source_until、generated_at和algorithm_version；同快照在批分或考勤更正后仍与原页面一致，新查询才反映更正。

快照标识不是授权凭据。读取与导出均检查user.active、当前课程成员/教师关系、创建者及保存的数据范围；不存在、跨课程、非创建者、已清理或当前不可访问统一404，学生调用教师导出接口403。仅允许读取kind为六个统计维度的analysis_run，warning批次不能用于此接口。历史快照是只读统计证据，不回写成绩；保留至课程验收后90天，由管理员按数据治理规则清理。快照不可用时提示重新查询，不能用最新数据冒充原快照。
- attendance：expected_count,present_count,late_count,leave_count,absent_count,attendance_rate=(present+late)/expected,performance_correlation,paired_count；分母为区间内已关闭任务的冻结名单；新增candidate_count,missing_performance_count,selected_paper_ids,correlation_reason；相关算法见第5.4节。
- knowledge：answered_count,correct_count,mastery,completed_knowledge_count,published_knowledge_count,progress,items:[{knowledge_id,title,answered_count,correct_count,wrong_count,mastery}]；items覆盖全部当前已发布知识点，按knowledge_id升序；wrong_count=answered_count−correct_count，零样本mastery=null。进度计数使用同一读取快照中的集合K={本课当前published=true知识点ID}：published_knowledge_count=|K|，completed_knowledge_count=|K与本人completed=true记录的交集|，progress为两者之比，K空时null。历史下架知识点的记录保留但分子分母均排除，重新发布时仍按保留的完成状态计入；日期from/to仅筛选作答，不筛选完成进度或K，返回population_basis注明进度是当前快照。只计实际作答的客观题，漏答不混入掌握度，按每次practice_attempt及paper answer去重计数；同一答卷更正不生成第二样本。多标签按PRD口径。
- wiring：assigned_count,completed_student_count,completion_rate,attempt_count,error_counts；completed必须功能全过，错误同attempt/revision/code只计一次。
- grading：student_count,submission_count,effective_count,accepted_count,pass_rate,mean_score,score_bins,run_count,system_error_count,timeout_count,resource_limit_count；教学分布每学生/实验版本取有效成绩，run可靠性另外计算，不混分母；结果按suite_id分组。
- resources：resource_id,version_id,view_count,download_count,unique_users；intent=download只记download，intent=view只记view，同用户/event_id逻辑访问去重；列表浏览不计文件阅读；另返回items按资源分项。
- scores：kind:homework/exam/quiz（查询必需），paper_id?；expected_count,submitted_count,missing_count,graded_count,partial_count,mean_score,mean_percentage,score_bins；不同满分按百分比分箱[0,60)、[60,70)、[70,80)、[80,90)、[90,100]，原始均分仅同一paper有值；缺交不自动算0，pending不混入已批均分。
四人分工中010B承担scores，003承担resources；所有维度都支持同口径CSV。

### 5.2 问答与推荐

QA按当前已发布知识语料revision按需重建TF-IDF；重建失败返回503 INDEX_UNAVAILABLE，不返回旧内容；空语料found=false、matches=[]。推荐始终返回对象，items可为空，外层reason与source_until仍存在；确定算法及reason枚举见PRD第4.3节。

### 5.3 组卷与重放

组卷只返回草稿，不直接发布。请求采用二选一模型：首次传第5节字段及history_until?；重放仅传replay_of及新title，禁止同时覆盖约束/seed；响应含generation_snapshot_id。冻结候选最新版本（同question一份）、历史正确率/样本数、排序、约束、seed、算法版本；重放严格读取快照，不查新题库。配分用total_points*100整分，按选中顺序均分、余数给前若干题，每题至少1个百分之一分。不满足数量/配额/覆盖的确定矛盾422；搜索预算耗尽503 SEARCH_LIMIT，不能伪报无解。具体算法见PRD第4.2节；confidential同候选快照一起冻结。

GET /courses/{id}/analytics的from/to默认最近28天；事件按事件时间筛选，成绩及完成率按发布任务start_at选择任务、取source_until前结果。attendance细则见第5.4节。多实验样本为(student_id,experiment_version_id)，不等于自然人数。

预警model_status不足时仍可产生统计规则记录。警告批次生成读取一致数据快照，计算在写事务外完成，最后短事务保存全部快照/提示/幂等结果；同截止时间不是相同输入的保证，复现以保存快照为准。QA索引替换只在重建完成后原子更新revision，失败时不读旧索引。

### 5.4 考勤配对与识别验收

attendance-performance-v1的唯一计算定义及C01—C04见PRD第4.4节：同区间已关闭考勤任务按学生汇总，已评分homework/exam/quiz先换百分比再等权平均，按student_id配对Pearson。performance_paper_ids只允许attendance；kind/paper_id只允许scores；不适用参数400。source_until为服务器一致读取快照时间，to>source_until为400。班级未筛student_id时sample_size=candidate_count；教师student_id筛选只输出所选人的指标，相关性reason=personal_scope且不输出班级配对数，与学生范围一致。个人范围sample_size为本人有应到任务时1否则0，candidate_count/paired_count/missing_performance_count均null；班级范围指标始终存在。班级paired_count不足3优先insufficient_pairs，零方差zero_variance，否则ok；r无单位、[-1,1]、展示6位，rate为0—1、performance_mean_percentage为0—100；缺分母null。metrics另含performance_mean_percentage（按有效配对学生等权）及各排除计数；series也使用同一口径。warnings包含“相关性不代表因果，不自动扣分”。CSV与页面同一源快照，不输出学生无权查看的班级数据。

识别算法recognition-template-v1、二值掩膜交并比、0.55识别下限及0.85低置信度分界、固定字典、bbox约束和F01—F05见PRD第4.5节。低置信度是recognized项的confidence_band=low，不另造数据库状态；零项unrecognized。POST confirm仅原提交者，空数组允许；symbol限NOT/AND/OR/XOR，label限固定字典，非法框/枚举400，重复确认409，越权404。确认只存结构草稿，不推断网表/成绩。模型中的算法版本与模板哈希由服务端生成，不允许请求覆盖。

## 6 实验与连线接口 SPEC-009/017

ExperimentVersion读模型：id、experiment_id、version、title、objectives、knowledge_ids、instructions、submission_modes（wiring/circuit的非空子集）、panel（components及terminals，wiring模式必需）、rules、judge_profile_id（服务端派生；circuit草稿未配置时为null，已发布circuit版本必须非空，wiring-only版本为null）、published_at。端子字段id字符串、component_id字符串、name、direction枚举in/out、width整数1—8、required布尔。每版本发布后不可变，teacher可创建新版本。

Wire模型：id字符串、from_terminal、to_terminal；State模型：wires数组、inputs映射（所有SWITCH及面板存在的RESET/ENABLE源OUT端子ID到整数；SWITCH按位宽取值，RESET/ENABLE仅0或1，禁止CLOCK键）、registers映射、phase、tick。state整体由服务端按PRD第6.1节重放校验，不能单独更改registers/phase/tick；GET返回持久化的权威状态。

Action模型：seq正整数、type、payload、client_at。type为connect时payload为Wire，disconnect为wire_id，set_input为terminal_id/value，step/reset为无字段，undo/redo为target_seq；seq连续递增，client_at仅作提示，服务端received_at用于记录。一次请求新增动作不超过500，整个attempt不超过10000。

| 方法与路径 | 入参 | 返回 | 权限/特例 |
|---|---|---|---|
| GET /courses/{id}/experiments | 分页 | 实验及最新已发布版本 | L |
| POST /courses/{id}/experiments | code:EXP-01/EXP-02/EXP-03/EXP-04,title,description | {id,title} | T |
| POST /experiments/{id}/versions | title,objectives,knowledge_ids,instructions,submission_modes,panel?,rules；不接收judge_profile_id或其他服务端派生字段 | 新draft版本，judge_profile_id=null | T；wiring模式必须提供panel；检查panel/rules/schema；circuit草稿允许尚无评测配置 |
| POST /experiment-versions/{id}/publish | start_at,end_at,initial_test_suite_id?（circuit必需） | 已发布版本 | T；wiring模式需端子和规则完整，circuit模式需判分配置齐全且测试集验证通过；不支持的提交模式返回409 |
| GET /experiment-versions/{id} | 无 | 脱敏ExperimentVersion | L；学生不可见隐藏rules答案与测试集 |
| POST /experiment-versions/{id}/wiring-attempts | 无 | WiringAttempt:{id,revision:0,status:draft,state,latest_seq:0} | S |
| GET /wiring-attempts/{id} | 无 | WiringAttempt、actions摘要、saved_at | 本人/T |
| PUT /wiring-attempts/{id} | revision,state,actions | {id,revision:旧值+1,latest_seq,saved_at} | 本人S；旧revision409；服务端重放结果须与state一致，否则422 STATE_MISMATCH；同批状态/动作原子保存 |
| POST /wiring-attempts/{id}/validate | revision | {valid,errors:[{code,terminal_ids,wire_ids,message}],revision} | 本人；数据冲突409，合法请求但错误连线返回200且valid=false |
| POST /wiring-attempts/{id}/submit | revision；Idempotency-Key | {id,status:submitted,snapshot_hash,submitted_at,validation,completed,functional_results} | 本人；结构验证失败422；结构合法时保存功能结果，completed表示功能是否全部通过；已提交不得编辑 |
| GET /wiring-attempts/{id}/actions | after_seq?:0起，page_size≤500 | {items,latest_seq,next_after_seq} | 本人/T；按seq读取 |
| GET /courses/{id}/wiring-attempts | experiment_version_id?,student_id?,status?,分页 | WiringAttempt列表含completed | T班级/S本人；业务规则见第6节连线模型；空结果见第1节分页 |
| GET /courses/{id}/experiment-versions | experiment_id?,status?,分页 | ExperimentVersion列表 | T全量/S已发布且在参与名单 |

错误定位code为TERMINAL_NOT_FOUND、WIDTH_MISMATCH、OUTPUT_CONFLICT、REQUIRED_OPEN、DUPLICATE_WIRE、SELF_CONNECTION、UNSTABLE_SIGNAL。运行和逐步预览在浏览器执行；持久化/最终校验通过上述接口，不为每一条导线建立网络请求。


运行配置与字段细则：ExperimentVersion写模型须包含submission_modes及适用模式所需的panel/rules，实验code通过Experiment继承；顶层评分模板由code固定，发布时校验模式组合。code属于Experiment，创建Experiment入参为code/title/description，版本通过experiment_id继承，不另设可变code。GET实验列表对教师返回draft及published摘要，学生只返回参与名单内published；ExperimentVersion响应另含start_at/end_at/participant_count。教师draft修改采用新建版本，不提供原地改已发布内容。

## 7 在线评测接口 SPEC-018

Submission公开模型：id、experiment_version_id、filename（清洗后的展示名）、file_sha256、file_size、created_at、latest_run、effective_run。Run公开模型：id、status、score（null或0—100）、passed_count、executed_count、total_count、public_cases、hidden_summary、engine_version、test_suite_version、started_at、finished_at、error_code。公开用例包含label/input/expected/actual/passed；隐藏用例只给汇总和故障类别。排队/运行中不得返回已有旧分数冒充当前结果。

| 方法与路径 | 入参 | 返回 | 权限/特例 |
|---|---|---|---|
| POST /experiment-versions/{id}/submissions | multipart:file（单个.circ≤2MiB）；Idempotency-Key必需 | 202 {submission_id,run_id,status:queued,status_url} | S；权限、大小、内容、端口预检先于入队；429/503明确可重试 |
| GET /submissions/{id} | 无 | Submission及latest_run、effective_run | 本人/T |
| GET /submissions/{id}/runs | 分页 | Run列表 | 本人/T；不泄漏原始沙箱日志 |
| GET /grading-runs/{id} | 无 | Run | 本人/T；建议客户端2秒轮询，终态停止 |
| GET /courses/{id}/submissions | experiment_id?,student_id?,status?，分页 | Submission列表 | T班级/S本人；业务规则见第7节评测模型；空结果见第1节分页 |
| POST /submissions/{id}/regrades | reason:1—500，test_suite_id?；Idempotency-Key | 202 {submission_id,run_id,status} | T；仅选本实验版本已发布且验证有效的suite主键；省略时选受理时active_suite_id；旧run不变 |
| GET /submissions/{id}/file | 无 | 原始.circ字节下载 | 本人/T；强制附件，不内联XML |
| POST /experiment-versions/{id}/test-suites | cases:[{label,visibility,group_code,steps}] | {id,version,status:draft,total_count} | T；学生不能访问；每组至少一例；返回scoring_groups；不接受weight/engine_version/limits覆盖 |
| PUT /experiment-versions/{id}/judge-profile | top_circuit,port_schema,allowed_components,engine_version,limits | JudgeProfile:{id,...入参} | T；仅含circuit模式的draft实验版本，首次创建、后续更新本版本唯一配置；仅wiring或已发布版本409；受管理员允许引擎/最大限额限制 |
| POST /experiment-versions/{id}/reference-files | file（.circ），kind:correct/known_wrong | {file_id,sha256,kind} | T；与学生文件同样隔离校验，教师身份不绕过沙箱 |
| POST /test-suites/{id}/validations | reference_file_id,negative_file_id | 202 {validation_id,status:queued} | T；异步验证标准电路全过、已知错误电路至少一项失败 |
| GET /test-suite-validations/{id} | 无 | {id,status,reference_result,negative_result,error_code} | T；status=queued/running/passed/failed/system_error |
| POST /test-suites/{id}/publish | validation_id | {id,version,status:published} | T；只有与当前suite/profile/JAR/标准及反例文件全部哈希一致且passed的验证可发布；否则409 |
| GET /test-suites/{id} | 无 | 完整测试集 | T；隐藏数据仅教师管理面可见，不写公共日志 |
| GET /experiment-versions/{id}/test-suites | status?,分页 | suite版本、状态、scoring_groups、validation_id | T |
| PUT /experiment-versions/{id}/active-test-suite | test_suite_id,revision | {test_suite_id,revision:旧值+1} | T；同版本已发布且验证有效；事务校验，revision过期409 |
| GET /experiment-versions/{id}/reference-files | 分页 | {file_id,kind,sha256}列表 | T |

steps为有序向量数组：step_no、inputs（除CLK以外的输入标签→整型）、expected（输出标签→整型或明确允许的X/Z）、clock_event（none/rising/falling）。每个case就是独立sequence，先初始化并同步复位；case内保持状态。inputs禁止CLK；输入先稳定，再施加clock_event，传播稳定后采样。相同方向边沿连续出现必须插入反向边沿，不隐式制造边沿。组合ALU不复位，clock_event固定none。不能把“无关位”默认应用于所有输出。上述为平台内部测试契约，实际转换至固定引擎格式由适配层承担，不能让学生提供CLI参数。

测试集draft也作为一次完整快照保存；修改用例创建新draft版本，不允许复用旧验证报告。评分组及组内等权按PRD定义，使用group_code；组满分由固定实验模板生成，不接受客户端weight或组满分。每个group至少一个case，所有必需评分组齐全才可验证发布。教师验证任务与学生任务共用限额沙箱但分别持久化，不能拿教师标准答案当学生成绩。

幂等键为UUID格式字符串，作用域为用户+操作类型，保留24小时。请求指纹包含实验版本及文件SHA（重评包括目标测试集），同键同指纹返回原ID，同键不同指纹409；数据库唯一约束防并发竞态。频率/容量控制与入队在短事务中完成。上传字节安全落盘后写入submission与首个run，同事务提交；失败清理孤儿文件，不能返回一个丢失文件的任务。

公开终态码：ACCEPTED、WRONG_ANSWER、TIME_LIMIT、MEMORY_LIMIT、OUTPUT_LIMIT、CIRCUIT_LOAD_ERROR、ENGINE_UNAVAILABLE、ENGINE_CRASH、INCOMPLETE_RESULT、WORKER_LOST。TIME_LIMIT映射timeout；MEMORY_LIMIT/OUTPUT_LIMIT映射resource_limit；CIRCUIT_LOAD_ERROR映射invalid_circuit；最后四种为system_error、score=null。终态判定优先级见PRD第7.1节。预检失败无submission时仍返回request_id，供教师定位。


实验配置顺序固定为创建draft版本→PUT本版本judge-profile→创建测试集和参考文件→验证并发布测试集→发布实验版本。judge_profile_id按judge_profile.experiment_version_id的唯一关联派生，创建请求传入该字段即400，不能绑定其他版本的配置。circuit草稿无配置时可读取、创建测试集和上传参考文件，但发起测试集验证返回409 STATE_CONFLICT；配置后修改任一执行身份仍使旧验证失效。实验首次发布请求还需initial_test_suite_id（仅circuit模式），同事务确认配置存在且完整、suite已发布且完整验证身份匹配当前profile，否则409 STATE_CONFLICT且版本保持draft；成功后冻结配置并建立experiment_grading.active_suite_id。后续切换仅改独立绑定，不修改实验内容。入队事务锁定active_suite_id及profile/JAR/suite哈希到run；worker只能使用此快照。重评目标必须同experiment_version_id，不以端口相似允许跨实验；同时最多一个queued/running的run/submission，学生每实验活动上限和全局队列上限也适用于重评。管理员retry仅重试system_error，原suite/profile不变，整条重试链最多2次；教师重评可换suite，但相同suite的system_error再次执行必须retry_of引用原链并计该链上限，不得换接口绕过。

latest_run为该submission创建序号最大的run；effective_run为最大序号且处于accepted/wrong_answer/timeout/resource_limit/invalid_circuit的run，可能null。queued/running/system_error不覆盖既有有效结果。教学成绩取同学生/实验版本按(created_at,id)倒序首个具有effective_run的submission；报告同时展示最新提交待评情况，不伪装旧分为新结果。

## 8 运维接口及契约变更

GET /health仅返回{web_ready,db_ready,grader_ready,status}，任一必需单元不可用返回503，不返回路径或版本敏感信息。GET /admin/grading-runs支持status、分页，仅A；POST /admin/grading-runs/{id}/retry仅A、reason必需、产生新run、不改旧结果。GET /admin/audit-events仅A，按actor、action、日期分页。

接口破坏性修改先更新本契约、PRD验收与DBD，再评审开发；已发布实验/测试版本不原地改。前端、后端及测试负责人在同一PR记录兼容与迁移影响。系统运行中外部客户端不得调用worker内部领任务/续租逻辑，它不暴露为公网API。

## 9 跨模块参与名单与通知

考勤创建、试卷发布、实验版本发布分别冻结当时active学生名单。实验publish入参增加start_at,end_at（start<end），返回participant_count；学生仅名单内且start≤now<end可新建或提交实验记录。历史退课不改分母；新加入者只参与之后发布的任务。学生退出后失去当前课程访问，历史留存供教师审计。发布/撤回/替代备课、发布实验、测验提醒、请假审批/更正、考勤关闭后的迟到/缺勤均复用notification；同业务事件/接收人只生成一次。

补充通知不提供外部邮件/短信发送。课程创建若尚无学生，任务发布返回422 EMPTY_PARTICIPANTS，避免零人任务被视为完成；知识/资源可在无学生时准备。实验窗口结束后禁止新提交但教师重评及管理员系统故障重试仍允许，受相同活动任务/队列约束；学生同键成功重放按第11节优先处理。

## 10 契约检索

身份和课程授权见第2节；考勤、资源与备课见第3节；作答、测评、演示见第4节；分析与智能模型见第5节；实验和连线见第6节；评测身份与有效结果见第7节。公共协议见第1节，冻结名单与通知见第9节，幂等受理见第11节。本节仅提供索引，不另存覆盖业务定义的字段。

## 11 公共受理与幂等

幂等执行顺序：身份及当前对象授权→文件大小/基础语法→查键并比对指纹→已有成功请求重放→新请求才检查窗口、revision、活动数、频率及容量→业务事务和幂等记录一起提交。保留24小时；到期可重新受理但业务唯一约束仍有效。返回首次成功的状态码及响应快照，最新状态另GET；不会在重放时重新扣限额。UUID键作用域为(user_id,operation,key)，JSON键排序、答案按question_version_id排序，字符串不改语义。

| operation | 指纹（还含路径目标ID） |
|---|---|
| paper_attempt（含quiz别名） | paper_id + 规范化answers；两个入口使用相同operation |
| practice_attempt | question_id + question_version_id + answer |
| wiring_submit | attempt_id + revision |
| circuit_submit | experiment_version_id + 文件SHA；不含受理时选择的suite，重放不受当前suite切换影响 |
| circuit_regrade | submission_id + reason + 显式test_suite_id或固定标记active；首次解析出的实际suite存响应 |
| grader_retry | 原run_id + reason |
| question_import | resource_version_id + 文件SHA |
| warning_run | course_id + from/to（source_until由首次请求确定） |

admin retry也必须Idempotency-Key；同一请求失败4xx/503不保留成功键。启动/关闭这类天然幂等状态操作返回现态，revision写操作仍使用乐观锁。教学数据查询不能绕开对象所属模块直接读取原始file或隐藏test_case。
