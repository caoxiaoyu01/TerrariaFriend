using System;

namespace TerrariaFriend.AgentCommunication
{
	// Agent 地址与网络参数
	public static class AgentConfiguration
	{
		public static readonly Uri TriggerEndpoint = new Uri("http://127.0.0.1:8000/agent/trigger");

		// C# → Python HTTP 请求的最长等待时间 30 秒
		public static readonly TimeSpan RequestTimeout = TimeSpan.FromSeconds(30);
	}
}
