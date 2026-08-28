using System;

namespace TerrariaFriend.AgentCommunication
{
	// 智能体服务地址和网络设置
	public static class AgentConfiguration
	{
		public static readonly Uri TriggerEndpoint = new Uri("http://127.0.0.1:8000/agent/trigger");
		public static readonly Uri WorldSessionEndedEndpoint = new Uri("http://127.0.0.1:8000/agent/world-session-ended");

		// 一次推理最多调用模型四轮
		public static readonly TimeSpan RequestTimeout = TimeSpan.FromSeconds(120);
		public static readonly TimeSpan BoundarySignalTimeout = TimeSpan.FromSeconds(5);
	}
}
