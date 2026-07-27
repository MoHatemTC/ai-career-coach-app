import React, { useState } from 'react';

const ChatWindow = () => {
  // حالة لحفظ المحادثة بين المستخدم والبوت
  const [messages, setMessages] = useState([
    { sender: 'bot', text: 'Hello! I can help you find job matches today.' }
  ]);
  const [isLoading, setIsLoading] = useState(false);

  // الدالة اللي بتشتغل لما ندوس على زرار Trigger Now
  const handleTriggerNow = async () => {
    setIsLoading(true);
    
    // 1. نضيف رسالة المستخدم للشات
    setMessages(prev => [...prev, { sender: 'user', text: 'Trigger job matching now.' }]);

    try {
      // 2. نكلم الـ API اللي عملتيه في الباك إند (FastAPI بيشتغل افتراضياً على بورت 8000)
      const response = await fetch('http://127.0.0.1:8000/api/trigger-matching', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: 'user_1' })
      });

      const data = await response.json();

      // 3. نجهز رسالة الرد من الداتا اللي راجعة
      if (data.success) {
        let botReply = data.message;
        if (data.jobs && data.jobs.length > 0) {
          botReply += '\n\n' + data.jobs.map(job => `🔹 ${job.title} at ${job.company}`).join('\n');
        }
        // نضيف الرد للشات
        setMessages(prev => [...prev, { sender: 'bot', text: botReply }]);
      }
    } catch (error) {
      setMessages(prev => [...prev, { sender: 'bot', text: 'Sorry, could not connect to the Backend server.' }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div style={{ padding: '20px', maxWidth: '400px', margin: '50px auto', border: '1px solid #ddd', borderRadius: '10px', fontFamily: 'Arial, sans-serif' }}>
      <h3 style={{ textAlign: 'center', margin: '0 0 15px 0' }}>Job Matching Bot</h3>
      
      {/* منطقة عرض الرسائل */}
      <div style={{ height: '350px', overflowY: 'auto', marginBottom: '15px', backgroundColor: '#f9f9f9', padding: '15px', borderRadius: '8px' }}>
        {messages.map((msg, idx) => (
          <div key={idx} style={{ textAlign: msg.sender === 'user' ? 'right' : 'left', margin: '10px 0' }}>
            <span style={{ 
              background: msg.sender === 'user' ? '#007bff' : '#e4e6eb', 
              color: msg.sender === 'user' ? 'white' : 'black',
              padding: '10px 15px', 
              borderRadius: '15px', 
              display: 'inline-block',
              whiteSpace: 'pre-wrap',
              maxWidth: '80%'
            }}>
              {msg.text}
            </span>
          </div>
        ))}
        {isLoading && <div style={{ textAlign: 'left', color: '#888' }}><em>Bot is typing...</em></div>}
      </div>
      
      {/* زرار الـ Trigger Now المطلوب في التاسك */}
      <button 
        onClick={handleTriggerNow} 
        disabled={isLoading}
        style={{ 
          width: '100%', 
          padding: '12px', 
          backgroundColor: isLoading ? '#ccc' : '#28a745', 
          color: 'white', 
          border: 'none', 
          borderRadius: '5px', 
          cursor: isLoading ? 'not-allowed' : 'pointer',
          fontWeight: 'bold',
          fontSize: '16px'
        }}
      >
        {isLoading ? 'Finding Matches...' : 'Trigger Now'}
      </button>
    </div>
  );
};

export default ChatWindow;